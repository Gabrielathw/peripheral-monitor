# utils/icones.py
# Desenha os ícones do app (mouse, teclado, fone, microfone, tomada e monitor)
# dentro de um círculo, sempre perfeitamente centralizados, em qualquer computador.
from PIL import Image, ImageDraw

SUPER = 4  # desenha 4x maior e reduz depois (bordas lisas)


def _linha(d, pontos, largura, cor):
    """Linha com pontas arredondadas."""
    d.line(pontos, fill=cor, width=largura, joint="curve")
    r = largura / 2
    for x, y in (pontos[0], pontos[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=cor)


def gerar_icone(tipo, tamanho, cor_fundo, cor_icone):
    """Retorna uma imagem RGBA (círculo + ícone). tamanho = lado em pixels lógicos."""
    c = tamanho * SUPER
    u = c / 100.0  # unidade: o desenho usa coordenadas de 0 a 100

    img = Image.new("RGBA", (c, c), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if cor_fundo:
        d.ellipse((0, 0, c - 1, c - 1), fill=cor_fundo)

    w = max(2, int(4.2 * u))  # espessura do traço

    def P(x, y):
        return (x * u, y * u)

    def caixa(x1, y1, x2, y2):
        return (x1 * u, y1 * u, x2 * u, y2 * u)

    if tipo == "mouse":
        d.rounded_rectangle(caixa(35, 24, 65, 76), radius=15 * u, outline=cor_icone, width=w)
        _linha(d, [P(50, 24), P(50, 46)], w, cor_icone)
        _linha(d, [P(35, 46), P(65, 46)], w, cor_icone)
        d.rounded_rectangle(caixa(47.6, 31, 52.4, 40), radius=2.4 * u, fill=cor_icone)

    elif tipo == "teclado":
        d.rounded_rectangle(caixa(21, 32, 79, 68), radius=7 * u, outline=cor_icone, width=w)
        for cx in (31, 40.5, 50, 59.5, 69):
            d.rounded_rectangle(caixa(cx - 2.3, 39, cx + 2.3, 43.6), radius=1 * u, fill=cor_icone)
        for cx in (35.5, 45, 55, 64.5):
            d.rounded_rectangle(caixa(cx - 2.3, 47, cx + 2.3, 51.6), radius=1 * u, fill=cor_icone)
        d.rounded_rectangle(caixa(36, 56, 64, 60.6), radius=2 * u, fill=cor_icone)

    elif tipo == "audio":  # fone de ouvido
        d.arc(caixa(26, 24, 74, 72), start=180, end=360, fill=cor_icone, width=w)
        _linha(d, [P(26, 48), P(26, 56)], w, cor_icone)
        _linha(d, [P(74, 48), P(74, 56)], w, cor_icone)
        d.rounded_rectangle(caixa(21, 54, 34, 74), radius=5 * u, fill=cor_icone)
        d.rounded_rectangle(caixa(66, 54, 79, 74), radius=5 * u, fill=cor_icone)

    elif tipo == "microfone":
        d.rounded_rectangle(caixa(41, 22, 59, 56), radius=9 * u, outline=cor_icone, width=w)
        d.arc(caixa(32, 38, 68, 68), start=0, end=180, fill=cor_icone, width=w)
        _linha(d, [P(50, 68), P(50, 78)], w, cor_icone)
        _linha(d, [P(40, 78), P(60, 78)], w, cor_icone)

    elif tipo == "monitor":  # logo do app
        d.rounded_rectangle(caixa(21, 26, 79, 64), radius=6 * u, outline=cor_icone, width=w)
        _linha(d, [P(50, 64), P(50, 74)], w, cor_icone)
        _linha(d, [P(37, 74), P(63, 74)], w, cor_icone)
        _linha(d, [P(31, 46), P(41, 46), P(46, 37), P(53, 55), P(58, 46), P(69, 46)],
               max(2, int(3.4 * u)), cor_icone)

    else:  # "outros": tomada/plugue
        d.rounded_rectangle(caixa(36, 34, 64, 58), radius=6 * u, outline=cor_icone, width=w)
        _linha(d, [P(44, 22), P(44, 34)], w, cor_icone)
        _linha(d, [P(56, 22), P(56, 34)], w, cor_icone)
        _linha(d, [P(50, 58), P(50, 78)], w, cor_icone)

    return img
