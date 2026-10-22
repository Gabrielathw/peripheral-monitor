"""
DIAGNÓSTICO DE BATERIA
======================
Mostra EXATAMENTE o que o Windows informa de bateria para cada aparelho Bluetooth
conectado, e também tenta ler pelo outro caminho (BLE).

Como usar (com o aparelho conectado):
  1. Abra a pasta do projeto no VS Code
  2. Abra o terminal (menu Terminal > Novo Terminal)
  3. Digite:   python diagnostico_bateria.py
  4. Copie TUDO o que aparecer e me mande, junto com a porcentagem REAL do aparelho.
"""
import asyncio
import json
import subprocess

from utils.bluetooth_monitor import PS_CONECTADOS, NO_WINDOW

PS_NOS = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$chave = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$macs = @(__MACS__)
$todos = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue
$saida = @()
foreach ($mac in $macs) {
    foreach ($no in ($todos | Where-Object { $_.InstanceId -like "*$mac*" })) {
        $p = Get-PnpDeviceProperty -InstanceId $no.InstanceId -KeyName $chave -ErrorAction SilentlyContinue
        $valor = "(sem valor)"
        if ($p -and $null -ne $p.Data) { $valor = "$($p.Data)" }
        $saida += [PSCustomObject]@{ Mac = $mac; Id = $no.InstanceId; Classe = $no.Class; Nome = $no.FriendlyName; Bateria = $valor }
    }
}
if ($saida.Count -gt 0) { ConvertTo-Json -InputObject @($saida) }
"""


def ps(script, timeout=90):
    r = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                       encoding="utf-8", errors="ignore", timeout=timeout, creationflags=NO_WINDOW)
    if r.stderr.strip():
        print("  (aviso do PowerShell):", r.stderr.strip()[:300])
    if not r.stdout.strip():
        return []
    dados = json.loads(r.stdout)
    return [dados] if isinstance(dados, dict) else dados


async def ler_ble(nome):
    try:
        from bleak import BleakScanner, BleakClient
        achados = await BleakScanner.discover(timeout=4.0)
        candidatos = [d for d in achados if d.name and nome.lower() in d.name.lower()]
        if not candidatos:
            return "aparelho não apareceu no scan BLE (normal para fones/celulares em Bluetooth clássico)"
        for d in candidatos:
            try:
                async with BleakClient(d.address, timeout=4.0) as c:
                    v = await c.read_gatt_char("00002a19-0000-1000-8000-00805f9b34fb")
                    return f"{v[0]}%  (lido do serviço de bateria BLE)"
            except Exception as e:
                return f"apareceu no scan, mas não deu para ler a bateria: {type(e).__name__}"
    except Exception as e:
        return f"erro no BLE: {e}"


def main():
    print("Procurando aparelhos Bluetooth conectados...\n")
    aparelhos = ps(PS_CONECTADOS)
    if not aparelhos:
        print("Nenhum aparelho Bluetooth conectado.")
        return

    nos = ps(PS_NOS.replace("__MACS__", ",".join(f"'{a['Mac']}'" for a in aparelhos)))

    for a in aparelhos:
        print("=" * 70)
        print(f"APARELHO: {a['Name']}   (MAC {a['Mac']})")
        print("-" * 70)
        print("O que o Windows guarda (um item por 'nó' do aparelho):")
        meus = [n for n in nos if n["Mac"] == a["Mac"]]
        if not meus:
            print("  (nenhum nó encontrado)")
        for n in meus:
            print(f"  bateria = {n['Bateria']:<12} classe = {n['Classe'] or '-':<10} id = {n['Id']}")
        print("\nPlano B (BLE):", asyncio.run(ler_ble(a["Name"])))
        print()
    print("=" * 70)
    print("Agora me mande tudo isso + a porcentagem REAL que aparece no aparelho.")


if __name__ == "__main__":
    main()
