# utils/usb_monitor.py
import subprocess
import json
from utils.device_db import melhorar_nome, deve_ignorar

def obter_dispositivos_usb():
    dispositivos = []
    try:
        comando = r"[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-PnpDevice -PresentOnly -Status OK | Where-Object { $_.Class -match 'Mouse|Keyboard|AudioEndpoint|MEDIA|HIDClass' } | Select-Object FriendlyName, Class, InstanceId | ConvertTo-Json"
        resultado = subprocess.run(["powershell", "-Command", comando], capture_output=True, text=True, encoding='utf-8', errors='ignore')
        
        if resultado.stdout and resultado.stdout.strip():
            dados = json.loads(resultado.stdout)
            if isinstance(dados, dict): dados = [dados]
                
            vistos = set()
            for dev in dados:
                nome = dev.get("FriendlyName")
                classe = dev.get("Class")
                instance_id = dev.get("InstanceId", "")
                
                if not nome: continue
                if deve_ignorar(nome): continue
                if "BTHENUM" in instance_id or "BTHLE" in instance_id: continue
                
                tag = " [Notebook]" if instance_id.startswith("ACPI\\") else ""
                if instance_id.startswith("HID\\") and not instance_id.startswith("USB\\"):
                    tag = " [Notebook]"
                
                nome_melhorado = melhorar_nome(nome) + tag
                
                dev_id = f"{nome_melhorado}_{classe}"
                if dev_id not in vistos:
                    vistos.add(dev_id)
                    dispositivos.append({
                        "nome": nome_melhorado,
                        "fabricante": "Windows",
                        "tipo_conexao": "Cabo (USB)",
                        "status": "Conectado",
                        "bateria": None,
                        "classe": classe,
                        "id_sistema": instance_id,
                        "is_notebook": "[Notebook]" in nome_melhorado
                    })
    except Exception as e:
        print(f"Erro USB: {e}")
    return dispositivos