# utils/theme_manager.py
#
# Chaves obrigatórias: bg, card, text, accent, accent_hover, sidebar
# Chaves opcionais (usadas só se existirem):
#   accent_text   -> texto sobre botões/etiquetas de destaque (padrão: branco)
#   accent2       -> cor dos textos de status (padrão: azul)
#   title         -> cor dos títulos
#   border        -> cor da borda dos cartões (sem ela, não há borda)
#   track         -> fundo de barras, interruptores e itens "offline"
#   sub           -> texto secundário (padrão: cinza)
#   sidebar_text  -> texto da barra lateral (padrão: igual a "text")
#   sidebar_hover -> hover dos botões da barra lateral (padrão: igual a "card")
#   sidebar_title -> título da barra lateral (padrão: igual a "title")

THEMES = {
    "Creme & Roxo": {
        "bg": "#FFF4E6",            # Fundo creme
        "card": "#FDFEFF",          # Cartões brancos
        "text": "#19162B",          # Texto azul-noite
        "accent": "#FEB686",        # Pêssego
        "accent_hover": "#F99A5F",  # Pêssego mais forte (hover)
        "sidebar": "#19162B",       # Barra lateral azul-noite
        "accent_text": "#19162B",
        "accent2": "#4D4C6B",       # Roxo acinzentado (status)
        "title": "#19162B",
        "border": "#19162B",        # Contorno escuro nos cartões
        "track": "#FFE9C3",         # Creme (barras, itens offline)
        "sub": "#6A6986",
        "sidebar_text": "#FDFEFF",
        "sidebar_hover": "#4D4C6B",
        "sidebar_title": "#FEB686"
    },
    "Noite & Pêssego": {
        "bg": "#19162B",
        "card": "#4D4C6B",
        "text": "#FDFEFF",
        "accent": "#FEB686",
        "accent_hover": "#FFE9C3",
        "sidebar": "#221E3A",
        "accent_text": "#19162B",
        "accent2": "#FFE9C3",
        "title": "#FEB686",
        "border": "#FEB686",
        "track": "#6A6986",
        "sub": "#FFE9C3",
        "sidebar_text": "#FDFEFF",
        "sidebar_hover": "#4D4C6B"
    },
    "Preto & Roxo": {
        "bg": "#1E1E24",
        "card": "#2D2D35",
        "text": "#F8F4ED",
        "accent": "#9b87f5",
        "accent_hover": "#7c66df",
        "sidebar": "#25252B"
    },
    "Escuro Padrão": {
        "bg": "#212121",
        "card": "#2b2b2b",
        "text": "#ffffff",
        "accent": "#1f6aa5",
        "accent_hover": "#144870",
        "sidebar": "#1a1a1a"
    },
    "Claro Padrão": {
        "bg": "#f0f0f0",
        "card": "#ffffff",
        "text": "#000000",
        "accent": "#3a7ebf",
        "accent_hover": "#2b5e8c",
        "sidebar": "#e0e0e0"
    }
}
