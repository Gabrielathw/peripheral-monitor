# utils/historico.py
# Guarda os periféricos que já foram conectados, para mostrar na seção "Offs".
import json
import os
from datetime import datetime

PASTA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MeusPerifericos")
ARQUIVO = os.path.join(PASTA, "historico.json")


def carregar():
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            dados = json.load(f)
            return dados if isinstance(dados, dict) else {}
    except Exception:
        return {}


def salvar(historico):
    try:
        os.makedirs(PASTA, exist_ok=True)
        temporario = ARQUIVO + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            json.dump(historico, f, ensure_ascii=False, indent=2)
        os.replace(temporario, ARQUIVO)
    except Exception as e:
        print(f"Erro ao salvar histórico: {e}")


def registrar(historico, conectados):
    """Atualiza o histórico com tudo que está conectado agora."""
    agora = datetime.now().isoformat(timespec="seconds")
    for d in conectados:
        if "[Notebook]" in d["nome"]:
            continue  # itens internos do notebook não vão para o histórico
        entrada = historico.get(d["chave"], {})
        entrada.update({
            "nome": d["nome"],
            "tipo_conexao": d["tipo_conexao"],
            "classe": d.get("classe", ""),
            "categoria": d.get("categoria", "outros"),
            "icone": d.get("icone", "🔌"),
            "id_sistema": d.get("id_sistema", ""),
            "ultima_vez": agora,
            "desativado": False,
        })
        if d.get("bateria") is not None:
            entrada["ultima_bateria"] = d["bateria"]
        historico[d["chave"]] = entrada


def esquecer(historico, chave):
    historico.pop(chave, None)


def limpar(historico):
    historico.clear()
