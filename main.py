import re
import threading
import asyncio
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

from utils.usb_monitor import obter_dispositivos_locais
from utils.bluetooth_monitor import obter_dispositivos_bluetooth, STATUS_BT
from utils.theme_manager import THEMES
from utils import historico, actions, icones

ctk.set_appearance_mode("dark")

CATEGORIAS = [
    ("todos", "Todos", "✨"),
    ("audio", "Áudio", "🎧"),
    ("mouse", "Mouse", "🖱️"),
    ("teclado", "Teclado", "⌨️"),
    ("outros", "Outros", "🔌"),
]

BATERIA_BAIXA = 20

# O app guarda o emoji de cada categoria; aqui ele vira o tipo de ícone desenhado
EMOJI_PARA_ICONE = {"🖱": "mouse", "⌨": "teclado", "🎧": "audio", "🎤": "microfone", "🔌": "outros"}


# ------------------------------------------------------------------ utilidades
def chave_dispositivo(nome):
    """Normaliza o nome para identificar o mesmo aparelho listado de formas diferentes.
    Ex.: 'Alto-falantes (Fone X) [Notebook]' -> 'fone x'
    """
    nome = nome.replace("[Notebook]", "").strip()
    m = re.search(r"\((.+)\)", nome)
    if m:
        nome = m.group(1)
    return nome.lower().strip()


def mesma_chave(a, b):
    if a == b:
        return True
    if len(a) >= 6 and len(b) >= 6:
        return a in b or b in a
    return False


def classificar(nome, classe=""):
    """Devolve (ícone, categoria) a partir do nome/classe do periférico."""
    n = nome.lower()
    c = str(classe).lower()
    palavras_mouse = ("mouse", "touchpad", "trackpad", "trackball", "mx master", "mx anywhere", "mx vertical",
                      "magic mouse", "g502", "g305", "g pro x superlight", "deathadder", "viper")
    palavras_teclado = ("keyboard", "teclado", "mx keys", "k380", "k780", "k400", "magic keyboard", "kbd")
    palavras_audio = ("audio", "áudio", "fone", "headphone", "headset", "earbud", "earphone", "buds", "airpods",
                      "pods", "speaker", "alto-falante", "caixa de som", "microfone", "microphone", "soundbar",
                      "jbl", "bose", "soundcore", "sony wh", "sony wf", "wh-1000", "wf-1000", "beats", "echo",
                      "boombox", "flip", "charge", "hyperx", "arctis", "cloud")
    if "mouse" in c or any(p in n for p in palavras_mouse):
        return "🖱️", "mouse"
    if "keyboard" in c or any(p in n for p in palavras_teclado):
        return "⌨️", "teclado"
    if any(p in n for p in ("microfone", "microphone")) and "headset" not in n:
        return "🎤", "audio"
    if any(p in n for p in palavras_audio) or "audio" in c or "media" in c:
        return "🎧", "audio"
    return "🔌", "outros"


def estimar_bateria(d):
    """Retorna (texto, valor_para_barra, aproximada).
    Valores 'em faixas' (0/20/40/60/80/100) do Windows: o celular informa a faixa de CIMA
    (ex.: real 26% -> 40%), então o valor real fica entre (faixa-19) e a faixa.
    """
    valor = d.get("bateria")
    if valor is None:
        return None, None, False
    if d.get("bateria_aprox"):
        if valor <= 0:
            return "≈ 0–10%", 5, True
        baixo = max(0, valor - 19)
        return f"≈ {baixo}–{valor}%", (baixo + valor) / 2, True
    return f"{valor}%", valor, False


def formatar_visto(iso):
    try:
        dt = datetime.fromisoformat(iso)
    except Exception:
        return "há algum tempo"
    hoje = datetime.now().date()
    hora = dt.strftime("%H:%M")
    if dt.date() == hoje:
        return f"hoje às {hora}"
    if (hoje - dt.date()).days == 1:
        return f"ontem às {hora}"
    return f"{dt.strftime('%d/%m/%Y')} às {hora}"


# ------------------------------------------------------------------ aplicativo
class MonitorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Peripheral Monitor")
        self.geometry("1020x760")
        self.minsize(860, 640)

        self.tema_atual = "Creme & Roxo"
        self.auto_update = True
        self.filtro_categoria = "todos"

        self._cache_icones = {}
        self.historico = historico.carregar()
        # Limpa entradas do formato antigo (itens USB/internos) para não duplicar
        for k in list(self.historico):
            e = self.historico[k]
            if (e.get("tipo_conexao") != "Bluetooth" and "|" not in k) or "[Notebook]" in e.get("nome", ""):
                del self.historico[k]
        historico.salvar(self.historico)
        self.conectados = []
        self.offline = []
        self.atualizando = False
        self.primeira_busca_feita = False

        self.configure(fg_color=THEMES[self.tema_atual]["bg"])
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.criar_sidebar()

        self.frame_conteudo = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_conteudo.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
        self.frame_conteudo.grid_rowconfigure(0, weight=1)
        self.frame_conteudo.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.criar_aba_inicio()
        self.criar_aba_configuracoes()
        self.mudar_aba("inicio")

        self.after(100, self.iniciar_atualizacao)
        self.after(30000, self.loop_atualizacao_automatica)

    # ---------------------------------------------------------- cores / estilos
    def t(self):
        return THEMES[self.tema_atual]

    def cor_destaque_texto(self):
        return self.t().get("accent_text", "#fff")

    def cor_titulo(self):
        t = self.t()
        return t.get("title", t["text"])

    def cor_sub(self):
        return self.t().get("sub", "#9ca3af")

    def cor_status(self):
        return self.t().get("accent2", "#60a5fa")

    def cor_trilha(self):
        return self.t().get("track", "#cbd5e1")

    def borda(self, largura=2):
        t = self.t()
        if "border" in t:
            return {"border_width": largura, "border_color": t["border"]}
        return {"border_width": 0}

    def estilo_botao_contorno(self):
        t = self.t()
        return dict(
            fg_color="transparent", text_color=t["text"],
            border_width=2, border_color=t.get("border", t["accent"]),
            hover_color=t.get("track", t["accent_hover"])
        )

    def criar_icone(self, parent, tipo, tamanho, cor_fundo, cor_icone):
        """Círculo com ícone desenhado, sempre centralizado."""
        chave = (tipo, tamanho, cor_fundo, cor_icone)
        imagem = self._cache_icones.get(chave)
        if imagem is None:
            pil = icones.gerar_icone(tipo, tamanho, cor_fundo, cor_icone)
            imagem = ctk.CTkImage(light_image=pil, dark_image=pil, size=(tamanho, tamanho))
            self._cache_icones[chave] = imagem
        return ctk.CTkLabel(parent, text="", image=imagem, width=tamanho, height=tamanho,
                            fg_color="transparent")

    # ---------------------------------------------------------- barra lateral
    def criar_sidebar(self):
        t = self.t()
        self.sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=t["sidebar"])
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(3, weight=1)

        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.grid(row=0, column=0, padx=20, pady=(30, 36), sticky="w")
        self.criar_icone(logo, "monitor", 48, t["accent"], self.cor_destaque_texto()).pack(side="left")
        ctk.CTkLabel(logo, text="Peripheral\nMonitor", justify="left", anchor="w",
                     font=("Segoe UI", 17, "bold"),
                     text_color=t.get("sidebar_title", self.cor_titulo())).pack(side="left", padx=12)

        self.btn_inicio = ctk.CTkButton(self.sidebar, text="🏠  Início", anchor="w", corner_radius=22, height=46,
                                        font=("Segoe UI", 14, "bold"), command=lambda: self.mudar_aba("inicio"))
        self.btn_inicio.grid(row=1, column=0, padx=20, pady=6, sticky="ew")

        self.btn_config = ctk.CTkButton(self.sidebar, text="⚙️  Configurações", anchor="w", corner_radius=22, height=46,
                                        font=("Segoe UI", 14, "bold"), command=lambda: self.mudar_aba("config"))
        self.btn_config.grid(row=2, column=0, padx=20, pady=6, sticky="ew")

        ctk.CTkLabel(self.sidebar, text="Periféricos do computador", font=("Segoe UI", 11),
                     text_color=t.get("sidebar_text", t["text"])).grid(row=4, column=0, padx=22, pady=(0, 22), sticky="w")

    def mudar_aba(self, nome_aba):
        for frame in self.frames.values():
            frame.grid_forget()
        self.frames[nome_aba].grid(row=0, column=0, sticky="nsew")

        t = self.t()
        for btn, nome in [(self.btn_inicio, "inicio"), (self.btn_config, "config")]:
            ativo = (nome == nome_aba)
            btn.configure(
                fg_color=t["accent"] if ativo else "transparent",
                text_color=self.cor_destaque_texto() if ativo else t.get("sidebar_text", t["text"]),
                hover_color=t["accent_hover"] if ativo else t.get("sidebar_hover", t["card"])
            )

    # ---------------------------------------------------------- aba Início
    def criar_aba_inicio(self):
        t = self.t()
        frame = ctk.CTkFrame(self.frame_conteudo, fg_color="transparent")
        self.frames["inicio"] = frame
        frame.grid_rowconfigure(4, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # Cabeçalho
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.grid_columnconfigure(0, weight=1)

        textos = ctk.CTkFrame(header, fg_color="transparent")
        textos.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(textos, text="Meus periféricos", font=("Segoe UI", 28, "bold"),
                     text_color=self.cor_titulo()).pack(anchor="w")
        self.lbl_resumo = ctk.CTkLabel(textos, text="Buscando dispositivos...", font=("Segoe UI", 13),
                                       text_color=self.cor_sub())
        self.lbl_resumo.pack(anchor="w")
        self.lbl_status = ctk.CTkLabel(textos, text="", font=("Segoe UI", 12, "bold"), text_color=self.cor_status())
        self.lbl_status.pack(anchor="w")

        self.btn_atualizar = ctk.CTkButton(
            header, text="🔄", width=50, height=50, corner_radius=25, font=("Segoe UI", 15),
            fg_color=t["accent"], hover_color=t["accent_hover"], text_color=self.cor_destaque_texto(),
            command=self.iniciar_atualizacao, **self.borda()
        )
        self.btn_atualizar.grid(row=0, column=1, sticky="e")

        # Busca
        self.entry_busca = ctk.CTkEntry(
            frame, placeholder_text="🔍  Pesquisar periférico...", corner_radius=22, height=46,
            fg_color=t["card"], text_color=t["text"], **self.borda()
        )
        self.entry_busca.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        self.entry_busca.bind("<KeyRelease>", self.filtrar_busca)

        # Filtros por categoria
        chips_frame = ctk.CTkFrame(frame, fg_color="transparent")
        chips_frame.grid(row=2, column=0, sticky="w", pady=(0, 12))
        self.chips = {}
        for chave, rotulo, emoji in CATEGORIAS:
            btn = ctk.CTkButton(chips_frame, text=f"{emoji} {rotulo}", width=100, height=36, corner_radius=18,
                                font=("Segoe UI", 12, "bold"),
                                command=lambda k=chave: self.definir_categoria(k))
            btn.pack(side="left", padx=(0, 8))
            self.chips[chave] = btn
        self.atualizar_chips()

        # Cartões-resumo
        stats = ctk.CTkFrame(frame, fg_color="transparent")
        stats.grid(row=3, column=0, sticky="ew", pady=(0, 6))
        for i in range(3):
            stats.grid_columnconfigure(i, weight=1, uniform="stats")
        self.stat_labels = {}
        self.criar_stat(stats, 0, "on", "Conectados", "🟢", destaque=True)
        self.criar_stat(stats, 1, "off", "Offline", "⚪")
        self.criar_stat(stats, 2, "low", "Bateria baixa", "🪫")

        # Lista
        self.lista_frame = ctk.CTkScrollableFrame(
            frame, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=t["accent"], scrollbar_button_hover_color=t["accent_hover"]
        )
        self.lista_frame.grid(row=4, column=0, sticky="nsew")
        self.lista_frame.grid_columnconfigure(0, weight=1)

    def criar_stat(self, parent, coluna, chave, titulo, emoji, destaque=False):
        t = self.t()
        card = ctk.CTkFrame(parent, corner_radius=20,
                            fg_color=t["accent"] if destaque else t["card"], **self.borda())
        card.grid(row=0, column=coluna, sticky="ew",
                  padx=(0 if coluna == 0 else 6, 0 if coluna == 2 else 6))
        cor_txt = self.cor_destaque_texto() if destaque else t["text"]
        numero = ctk.CTkLabel(card, text="0", font=("Segoe UI", 28, "bold"), text_color=cor_txt)
        numero.pack(anchor="w", padx=18, pady=(10, 0))
        ctk.CTkLabel(card, text=f"{emoji} {titulo}", font=("Segoe UI", 12), text_color=cor_txt).pack(
            anchor="w", padx=18, pady=(0, 10))
        self.stat_labels[chave] = numero

    def definir_categoria(self, chave):
        self.filtro_categoria = chave
        self.atualizar_chips()
        self.renderizar_lista_inicio()

    def atualizar_chips(self):
        t = self.t()
        for chave, btn in self.chips.items():
            if chave == self.filtro_categoria:
                btn.configure(fg_color=t["accent"], text_color=self.cor_destaque_texto(),
                              hover_color=t["accent_hover"],
                              border_width=2, border_color=t.get("border", t["accent"]))
            else:
                btn.configure(fg_color=t["card"], text_color=t["text"],
                              hover_color=t.get("track", t["accent_hover"]),
                              border_width=2, border_color=t.get("border", t["card"]))

    # ---------------------------------------------------------- aba Configurações
    def cartao_config(self, parent, titulo, descricao):
        t = self.t()
        card = ctk.CTkFrame(parent, corner_radius=22, fg_color=t["card"], **self.borda())
        card.pack(fill="x", pady=8)
        ctk.CTkLabel(card, text=titulo, font=("Segoe UI", 16, "bold"), text_color=t["text"]).pack(
            anchor="w", padx=20, pady=(16, 0))
        ctk.CTkLabel(card, text=descricao, font=("Segoe UI", 12), text_color=self.cor_sub(),
                     anchor="w", justify="left", wraplength=560).pack(anchor="w", padx=20, pady=(2, 10))
        return card

    def criar_aba_configuracoes(self):
        t = self.t()
        frame = ctk.CTkFrame(self.frame_conteudo, fg_color="transparent")
        self.frames["config"] = frame

        ctk.CTkLabel(frame, text="Configurações", font=("Segoe UI", 28, "bold"),
                     text_color=self.cor_titulo()).pack(anchor="w", pady=(0, 10))

        # Aparência
        card = self.cartao_config(frame, "🎨  Aparência", "Escolha as cores do aplicativo.")
        self.combo_temas = ctk.CTkOptionMenu(
            card, values=list(THEMES.keys()), corner_radius=16, height=40,
            fg_color=t.get("track", t["card"]), button_color=t["accent"], button_hover_color=t["accent_hover"],
            text_color=t["text"], dropdown_fg_color=t["card"], dropdown_text_color=t["text"],
            dropdown_hover_color=t.get("track", t["accent_hover"]), command=self.mudar_tema
        )
        self.combo_temas.set(self.tema_atual)
        self.combo_temas.pack(anchor="w", padx=20, pady=(0, 18))

        # Atualização
        card = self.cartao_config(frame, "🔄  Atualização", "Atualiza a lista de periféricos sozinho a cada 30 segundos.")
        opcoes = {"fg_color": t["track"]} if "track" in t else {}
        self.switch_auto = ctk.CTkSwitch(card, text="Atualização automática", text_color=t["text"],
                                         progress_color=t["accent"], command=self.toggle_auto_update, **opcoes)
        if self.auto_update:
            self.switch_auto.select()
        else:
            self.switch_auto.deselect()
        self.switch_auto.pack(anchor="w", padx=20, pady=(0, 18))

        # Histórico
        card = self.cartao_config(frame, "🕘  Histórico",
                                  "Os periféricos que já foram conectados ficam salvos para aparecer na seção Offs.")
        self.btn_limpar = ctk.CTkButton(card, text="🗑️  Limpar histórico", height=38, corner_radius=19,
                                        font=("Segoe UI", 13, "bold"), width=190,
                                        command=self.limpar_historico, **self.estilo_botao_contorno())
        self.btn_limpar.pack(anchor="w", padx=20, pady=(0, 18))

    def mudar_tema(self, novo_tema):
        self.tema_atual = novo_tema
        self.configure(fg_color=self.t()["bg"])

        self.frame_conteudo.destroy()
        self.sidebar.destroy()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.criar_sidebar()

        self.frame_conteudo = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_conteudo.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
        self.frame_conteudo.grid_rowconfigure(0, weight=1)
        self.frame_conteudo.grid_columnconfigure(0, weight=1)

        self.frames = {}
        self.criar_aba_inicio()
        self.criar_aba_configuracoes()
        self.mudar_aba("config")

        if self.primeira_busca_feita:
            self.renderizar_tudo()
        self.iniciar_atualizacao()

    def toggle_auto_update(self):
        self.auto_update = self.switch_auto.get() == 1

    def limpar_historico(self):
        if not messagebox.askyesno("Limpar histórico",
                                   "Apagar o histórico de periféricos que já foram conectados?\n\n"
                                   "Os que estão conectados agora continuam aparecendo."):
            return
        historico.limpar(self.historico)
        historico.registrar(self.historico, self.conectados)
        historico.salvar(self.historico)
        self.offline = self.calcular_offline()
        self.renderizar_tudo()

    # ---------------------------------------------------------- busca de dispositivos
    def loop_atualizacao_automatica(self):
        if self.auto_update:
            self.iniciar_atualizacao()
        self.after(30000, self.loop_atualizacao_automatica)

    def iniciar_atualizacao(self):
        if self.atualizando:
            return
        self.atualizando = True
        self.btn_atualizar.configure(state="disabled", text="⏳")
        if not self.primeira_busca_feita:
            for widget in self.lista_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.lista_frame, text="Buscando dispositivos, aguarde...",
                         text_color=self.t()["text"], font=("Segoe UI", 14)).grid(row=0, column=0, pady=40)
        threading.Thread(target=self.buscar_dispositivos, daemon=True).start()

    def buscar_dispositivos(self):
        filtrados = []
        try:
            locais, audio_inativo = obter_dispositivos_locais()
            bt = asyncio.run(obter_dispositivos_bluetooth())

            audio_ativo_nomes = [chave_dispositivo(d["nome"]) for d in locais if d.get("classe") == "AudioEndpoint"]
            audio_inativo_nomes = [chave_dispositivo(n) for n in audio_inativo]

            def tem(lista, alvo):
                return any(mesma_chave(alvo, n) for n in lista)

            # 1) Bluetooth: o Windows demora para perceber que um fone foi desligado,
            #    mas a saída de áudio dele some na hora. Se o aparelho tem saída de áudio
            #    e nenhuma está ativa, ele NÃO está conectado.
            resultado = []
            vistos = set()
            for d in bt:
                k = chave_dispositivo(d["nome"])
                if (tem(audio_ativo_nomes, k) or tem(audio_inativo_nomes, k)) and not tem(audio_ativo_nomes, k):
                    continue
                d["chave"] = k
                vistos.add(k)
                resultado.append(d)

            # 2) Itens locais (notebook, USB, P2, HDMI)
            nomes_bt = [chave_dispositivo(d["nome"]) for d in bt]
            for d in locais:
                if d["tipo_conexao"] == "Bluetooth":
                    continue  # saída de áudio de um aparelho Bluetooth: já tratado acima
                if d.get("classe") == "AudioEndpoint" and tem(nomes_bt, chave_dispositivo(d["nome"])):
                    continue
                k = f"{d['nome'].lower().strip()}|{d['tipo_conexao']}|{d.get('classe', '')}"
                if k in vistos:
                    continue
                vistos.add(k)
                d["chave"] = k
                resultado.append(d)

            for d in resultado:
                d["icone"], d["categoria"] = classificar(d["nome"], d.get("classe", ""))

            # Externos primeiro, itens internos do notebook por último
            filtrados = sorted(resultado, key=lambda d: d["tipo_conexao"].startswith("Notebook"))
        except Exception as e:
            print(f"Erro na busca: {e}")
            filtrados = []
        self.after(0, lambda: self.aplicar_resultado(filtrados))

    def aplicar_resultado(self, dispositivos):
        self.atualizando = False
        self.primeira_busca_feita = True
        self.conectados = dispositivos
        historico.registrar(self.historico, dispositivos)
        historico.salvar(self.historico)
        self.offline = self.calcular_offline()
        self.renderizar_tudo()

    def calcular_offline(self):
        chaves_on = [d["chave"] for d in self.conectados]
        offs = []
        for chave, entrada in self.historico.items():
            if chave in chaves_on:
                continue
            item = dict(entrada)
            item["chave"] = chave
            item["status"] = "Offline"
            item["bateria"] = None
            offs.append(item)
        offs.sort(key=lambda e: e.get("ultima_vez", ""), reverse=True)
        return offs

    # ---------------------------------------------------------- renderização
    def renderizar_tudo(self):
        try:
            self.btn_atualizar.configure(state="normal", text="🔄")
        except Exception:
            pass
        self.atualizar_resumo()
        self.renderizar_lista_inicio()

    def atualizar_resumo(self):
        n_on = len(self.conectados)
        n_off = len(self.offline)
        n_baixa = len([d for d in self.conectados
                       if estimar_bateria(d)[1] is not None and estimar_bateria(d)[1] < BATERIA_BAIXA])
        texto = f"{n_on} conectado(s)  •  {n_off} offline"
        if not STATUS_BT.get("radio_ligado", True):
            texto += "  •  Bluetooth desligado no Windows"
        self.lbl_resumo.configure(text=texto)
        self.stat_labels["on"].configure(text=str(n_on))
        self.stat_labels["off"].configure(text=str(n_off))
        self.stat_labels["low"].configure(text=str(n_baixa))

    def mostrar_status(self, mensagem, duracao=7000):
        try:
            self.lbl_status.configure(text=mensagem)
            self.after(duracao, lambda: self.lbl_status.winfo_exists() and self.lbl_status.configure(text=""))
        except Exception:
            pass

    def passa_filtro(self, d, termo):
        if self.filtro_categoria != "todos" and d.get("categoria", "outros") != self.filtro_categoria:
            return False
        return termo in d["nome"].lower() or termo in d.get("tipo_conexao", "").lower()

    def criar_secao(self, linha, titulo, quantidade, subtitulo=None):
        t = self.t()
        box = ctk.CTkFrame(self.lista_frame, fg_color="transparent")
        box.grid(row=linha, column=0, sticky="ew", padx=5, pady=(16, 2))
        topo = ctk.CTkFrame(box, fg_color="transparent")
        topo.pack(anchor="w")
        ctk.CTkLabel(topo, text=titulo, font=("Segoe UI", 19, "bold"), text_color=self.cor_titulo()).pack(side="left")
        ctk.CTkLabel(topo, text=str(quantidade), width=30, height=24, corner_radius=12, fg_color=t["accent"],
                     text_color=self.cor_destaque_texto(), font=("Segoe UI", 12, "bold")).pack(side="left", padx=10)
        if subtitulo:
            ctk.CTkLabel(box, text=subtitulo, font=("Segoe UI", 12), text_color=self.cor_sub(), anchor="w").pack(anchor="w")

    def criar_aviso_vazio(self, linha, texto):
        t = self.t()
        card = ctk.CTkFrame(self.lista_frame, corner_radius=22, fg_color=t["card"], **self.borda(1))
        card.grid(row=linha, column=0, sticky="ew", pady=6, padx=5)
        ctk.CTkLabel(card, text=texto, font=("Segoe UI", 13), text_color=self.cor_sub()).pack(padx=20, pady=18)

    def renderizar_lista_inicio(self):
        for widget in self.lista_frame.winfo_children(): widget.destroy()

        termo = self.entry_busca.get().lower() if self.entry_busca.winfo_exists() else ""
        
        # Separa em 3 grupos: Externos, Internos do Notebook, e Offlines
        externos = [d for d in self.conectados if not d.get("is_notebook", False) and self.passa_filtro(d, termo)]
        internos = [d for d in self.conectados if d.get("is_notebook", False) and self.passa_filtro(d, termo)]
        offs = [d for d in self.offline if self.passa_filtro(d, termo)]

        linha = 0
        # 1. Cartões Externos
        self.criar_secao(linha, "Conectados (Externos)", len(externos))
        linha += 1
        if not externos:
            self.criar_aviso_vazio(linha, "Nenhum periférico externo conectado.")
            linha += 1
        for d in externos:
            self.criar_card_dispositivo(linha, d, offline=False)
            linha += 1

        # 2. Cartões Internos (Notebook/PC)
        if internos:
            self.criar_secao(linha, "Drivers Internos (PC/Notebook)", len(internos), "Componentes nativos do computador.")
            linha += 1
            for d in internos:
                self.criar_card_dispositivo(linha, d, offline=False)
                linha += 1

        # 3. Cartões Offlines (Histórico)
        self.criar_secao(linha, "Offs (Histórico)", len(offs), "Já foram conectados antes, mas não estão em uso agora.")
        linha += 1
        if not offs:
            self.criar_aviso_vazio(linha, "Nenhum periférico offline no histórico.")
            linha += 1
        for d in offs:
            self.criar_card_dispositivo(linha, d, offline=True)
            linha += 1
            
        t = self.t()
        card = ctk.CTkFrame(self.lista_frame, corner_radius=22, fg_color=t["card"], **self.borda())
        card.grid(row=linha, column=0, sticky="ew", pady=6, padx=5)
        card.grid_columnconfigure(1, weight=1)

        icone = d.get("icone", "🔌")
        tipo_icone = EMOJI_PARA_ICONE.get(icone.replace("\ufe0f", ""), "outros")
        self.criar_icone(card, tipo_icone, 62,
                         self.cor_trilha() if offline else t["accent"],
                         t["text"] if offline else self.cor_destaque_texto()).grid(
            row=0, column=0, padx=(18, 14), pady=16)

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.grid(row=0, column=1, sticky="ew", pady=12, padx=(0, 18))

        # Nome + etiqueta do tipo de conexão
        linha_nome = ctk.CTkFrame(info, fg_color="transparent")
        linha_nome.pack(anchor="w")
        ctk.CTkLabel(linha_nome, text=d["nome"], font=("Segoe UI", 15, "bold"),
                     text_color=self.cor_sub() if offline else t["text"], anchor="w").pack(side="left")
        eh_bt = "Bluetooth" in d.get("tipo_conexao", "")
        if offline:
            fg_pill, txt_pill = self.cor_trilha(), t["text"]
        elif eh_bt:
            fg_pill, txt_pill = t["accent"], self.cor_destaque_texto()
        else:
            fg_pill, txt_pill = self.cor_trilha(), t["text"]
        ctk.CTkLabel(linha_nome, text=d.get("tipo_conexao", ""), font=("Segoe UI", 11, "bold"), height=22,
                     corner_radius=11, fg_color=fg_pill, text_color=txt_pill).pack(side="left", padx=10)

        # Status: só aparece nos offline (nos conectados, a etiqueta ao lado do nome já informa)
        if offline:
            linha_status = ctk.CTkFrame(info, fg_color="transparent")
            linha_status.pack(anchor="w", pady=(2, 0))
            ctk.CTkLabel(linha_status, text="●", font=("Segoe UI", 12), text_color=self.cor_sub()).pack(side="left")
            ctk.CTkLabel(linha_status, text=f" Offline  ·  visto por último {formatar_visto(d.get('ultima_vez', ''))}",
                         font=("Segoe UI", 12), text_color=self.cor_sub()).pack(side="left")

        # Bateria
        bateria = d.get("bateria")
        if offline:
            ultima = d.get("ultima_bateria")
            if ultima is not None:
                ctk.CTkLabel(info, text=f"🔋 Última leitura: {ultima}%", font=("Segoe UI", 11),
                             text_color=self.cor_sub(), anchor="w").pack(anchor="w", pady=(4, 0))
        elif bateria is not None:
            b_frame = ctk.CTkFrame(info, fg_color="transparent")
            b_frame.pack(anchor="w", pady=(6, 0))
            texto_bat, valor_barra, aprox = estimar_bateria(d)
            ctk.CTkLabel(b_frame, text=f"🔋 {texto_bat}", text_color=t["text"],
                         font=("Segoe UI", 12, "bold")).pack(side="left", padx=(0, 10))
            cor_barra = "#4ade80" if valor_barra > 30 else "#facc15" if valor_barra > BATERIA_BAIXA else "#f87171"
            opcoes = {"fg_color": t["track"]} if "track" in t else {}
            barra = ctk.CTkProgressBar(b_frame, width=170, height=10, corner_radius=5,
                                       progress_color=cor_barra, **opcoes)
            barra.pack(side="left")
            barra.set(valor_barra / 100)
            if aprox:
                ctk.CTkLabel(b_frame, text="estimativa", font=("Segoe UI", 11),
                             text_color=self.cor_sub()).pack(side="left", padx=(10, 0))
        elif eh_bt:
            ctk.CTkLabel(info, text="🔋 Bateria não informada por este aparelho", font=("Segoe UI", 11),
                         text_color=self.cor_sub(), anchor="w").pack(anchor="w", pady=(4, 0))

        # Botões de ação (a área só é criada se houver algum botão)
        if not offline:
            if "[Notebook]" not in d["nome"]:
                botoes = ctk.CTkFrame(card, fg_color="transparent", height=36)
                botoes.grid(row=0, column=2, padx=(8, 18))
                ctk.CTkButton(botoes, text="⏏  Desconectar", width=140, height=36, corner_radius=18,
                              font=("Segoe UI", 12, "bold"),
                              command=lambda d=d: self.desconectar(d),
                              **self.estilo_botao_contorno()).pack()
        else:
            botoes = ctk.CTkFrame(card, fg_color="transparent", height=36)
            botoes.grid(row=0, column=2, padx=(8, 18))
            if d.get("desativado"):
                ctk.CTkButton(botoes, text="🔌  Reativar", width=140, height=36, corner_radius=18,
                              font=("Segoe UI", 12, "bold"), fg_color=t["accent"],
                              text_color=self.cor_destaque_texto(), hover_color=t["accent_hover"],
                              command=lambda d=d: self.reativar(d)).pack(pady=(0, 6))
            ctk.CTkButton(botoes, text="🗑️  Esquecer", width=140, height=36, corner_radius=18,
                          font=("Segoe UI", 12, "bold"),
                          command=lambda d=d: self.esquecer(d),
                          **self.estilo_botao_contorno()).pack()

    def filtrar_busca(self, event=None):
        if not hasattr(self, "entry_busca") or not self.entry_busca.winfo_exists():
            return
        self.renderizar_lista_inicio()

    # ---------------------------------------------------------- ações
    def desconectar(self, d):
        aviso = ""
        if d.get("categoria") in ("mouse", "teclado") and "Bluetooth" not in d.get("tipo_conexao", ""):
            aviso = ("\n\nATENÇÃO: se este for o seu único mouse/teclado, você pode ficar "
                     "sem controle do computador.")
        if not messagebox.askyesno(
            "Desconectar",
            f"Desconectar \"{d['nome']}\"?\n\n"
            "O Windows vai pedir permissão de administrador. O periférico ficará desativado "
            "até você clicar em Reativar (na seção Offs)." + aviso
        ):
            return
        self.mostrar_status(f"Desconectando {d['nome']}...")
        threading.Thread(target=self.executar_acao, args=("desativar", d), daemon=True).start()

    def reativar(self, d):
        self.mostrar_status(f"Reativando {d['nome']}...")
        threading.Thread(target=self.executar_acao, args=("reativar", d), daemon=True).start()

    def executar_acao(self, acao, d):
        if acao == "desativar":
            ok, msg = actions.desativar(d)
        else:
            ok, msg = actions.reativar(d)
        self.after(0, lambda: self.pos_acao(acao, d, ok, msg))

    def pos_acao(self, acao, d, ok, msg):
        if not ok:
            self.mostrar_status("")
            messagebox.showwarning("Não foi possível concluir", msg)
            return
        entrada = self.historico.get(d["chave"])
        if entrada is not None:
            entrada["desativado"] = (acao == "desativar")
            historico.salvar(self.historico)
        if acao == "desativar":
            self.mostrar_status(f"Pedido enviado: {d['nome']} será desconectado.")
        else:
            self.mostrar_status(f"Pedido enviado: {d['nome']} reativado. Ligue o aparelho se necessário.")
        self.after(3000, self.iniciar_atualizacao)

    def esquecer(self, d):
        if not messagebox.askyesno("Esquecer periférico",
                                   f"Remover \"{d['nome']}\" do histórico de Offs?\n\n"
                                   "Se ele for conectado de novo, volta a aparecer."):
            return
        historico.esquecer(self.historico, d["chave"])
        historico.salvar(self.historico)
        self.offline = self.calcular_offline()
        self.renderizar_tudo()


if __name__ == "__main__":
    app = MonitorApp()
    app.mainloop()
