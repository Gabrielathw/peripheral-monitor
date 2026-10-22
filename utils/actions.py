# utils/actions.py
# Ações sobre os periféricos: desconectar (desativar) e reativar.
# Mexer em dispositivos exige permissão de administrador: o Windows vai mostrar
# a janela azul/amarela "Deseja permitir que este aplicativo faça alterações?".
import base64
import re
import subprocess

NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW


def _escapar(texto):
    return texto.replace("'", "''")


def _montar_script(dispositivo, acao):
    comando = "Disable-PnpDevice" if acao == "desativar" else "Enable-PnpDevice"
    alvo = (dispositivo.get("id_sistema") or "").strip()

    if "Bluetooth" in dispositivo.get("tipo_conexao", ""):
        # Para Bluetooth o alvo é o endereço MAC (12 caracteres hexadecimais)
        if not re.fullmatch(r"[0-9A-Fa-f]{12}", alvo):
            return None
        filtro = f"$_.InstanceId -like '*{alvo.upper()}*'"
    else:
        if len(alvo) < 8:
            return None
        filtro = f"$_.InstanceId -eq '{_escapar(alvo)}'"

    return (
        "$ErrorActionPreference = 'Continue'\n"
        f"Get-PnpDevice | Where-Object {{ {filtro} }} | ForEach-Object {{ {comando} -InstanceId $_.InstanceId -Confirm:$false }}\n"
    )


def _executar_como_admin(script):
    b64 = base64.b64encode(script.encode("utf-16-le")).decode()
    externo = (
        "$ErrorActionPreference = 'Stop'; "
        "Start-Process powershell -Verb RunAs -WindowStyle Hidden -Wait "
        f"-ArgumentList '-NoProfile','-EncodedCommand','{b64}'"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", externo],
            creationflags=NO_WINDOW, capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=120
        )
        if r.returncode != 0:
            return False, "A permissão de administrador foi negada ou cancelada."
        return True, ""
    except Exception as e:
        return False, f"Erro: {e}"


def desativar(dispositivo):
    script = _montar_script(dispositivo, "desativar")
    if script is None:
        return False, "Não consegui identificar este periférico com segurança."
    return _executar_como_admin(script)


def reativar(dispositivo):
    script = _montar_script(dispositivo, "reativar")
    if script is None:
        return False, "Não consegui identificar este periférico com segurança."
    return _executar_como_admin(script)
