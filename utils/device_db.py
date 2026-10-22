# utils/device_db.py
import json
import os

def carregar_db():
    caminho = os.path.join(os.path.dirname(__file__), "devices_db.json")
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"marcas": {}, "termos_ignorar": []}

def melhorar_nome(nome_original):
    db = carregar_db()
    nome_lower = nome_original.lower()
    
    for chave, marca in db["marcas"].items():
        if chave in nome_lower:
            return f"{marca} - {nome_original}"
            
    return nome_original

def deve_ignorar(nome_original):
    db = carregar_db()
    nome_lower = nome_original.lower()
    for termo in db["termos_ignorar"]:
        if termo.lower() in nome_lower:
            return True
    return False