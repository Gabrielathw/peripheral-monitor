# utils/bluetooth_monitor.py
import asyncio
import subprocess
import json
import time
from bleak import BleakScanner, BleakClient

# Evita que apareça uma janela preta do PowerShell piscando no app final
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

# Coloque True para ver no terminal o que o Windows devolveu
DEBUG = False

# Estado do rádio Bluetooth do Windows (atualizado a cada busca)
STATUS_BT = {"radio_ligado": True}

# Perfis Bluetooth de chamada (mãos-livres / headset). A bateria que o Windows pega
# desses perfis vem em apenas 5 faixas (0, 20, 40, 60, 80, 100%), portanto é aproximada.
PERFIS_CHAMADA = ("0000111E", "0000111F", "00001108", "00001112")

# A leitura exata (BLE) é guardada por 2 minutos para não ficar conectando toda hora
CACHE_BLE = {}
VALIDADE_BLE = 120

# Celulares informam a bateria ao Windows em apenas 5 faixas (0, 20, 40, 60, 80, 100%),
# por isso o valor deles é aproximado.
PALAVRAS_CELULAR = ("iphone", "ipad", "galaxy", "pixel", "xiaomi", "redmi", "poco", "motorola", "moto ",
                    "samsung", "huawei", "oneplus", "oppo", "realme", "celular", "phone", "android")

# Consulta a API WinRT do Windows e retorna SOMENTE aparelhos Bluetooth
# (clássicos e LE) com ConnectionStatus == Connected neste momento.
PS_CONECTADOS = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
    $task = $asTask.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

[Windows.Devices.Bluetooth.BluetoothDevice, Windows.Devices.Bluetooth, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Bluetooth.BluetoothLEDevice, Windows.Devices.Bluetooth, ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null

# Se o Bluetooth do Windows estiver DESLIGADO, o Windows "congela" a lista de conectados.
# Por isso verificamos o rádio primeiro: desligado = nenhum aparelho conectado.
$radioLigado = $true
try {
    [Windows.Devices.Radios.Radio, Windows.System.Devices, ContentType=WindowsRuntime] | Out-Null
    $radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
    $radiosBt = @($radios | Where-Object { $_.Kind -eq 'Bluetooth' })
    if ($radiosBt.Count -gt 0 -and @($radiosBt | Where-Object { $_.State -eq 'On' }).Count -eq 0) { $radioLigado = $false }
} catch { }
if (-not $radioLigado) { Write-Output 'RADIO_OFF'; exit 0 }

$status = [Windows.Devices.Bluetooth.BluetoothConnectionStatus]::Connected
$saida = @()

function Buscar($seletor, $tipo) {
    $res = Await ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($seletor)) ([Windows.Devices.Enumeration.DeviceInformationCollection])
    foreach ($d in $res) {
        # Segunda verificação: pergunta o status direto ao aparelho
        $confirmado = $true
        try {
            $dev = Await ($tipo::FromIdAsync($d.Id)) $tipo
            if ($dev) {
                $confirmado = ($dev.ConnectionStatus -eq 'Connected')
                $dev.Dispose()
            }
        } catch { }
        if ($confirmado) {
            $mac = $d.Id.Substring($d.Id.LastIndexOf('-') + 1).Replace(':', '').ToUpper()
            [PSCustomObject]@{ Name = $d.Name; Mac = $mac }
        }
    }
}

$saida += Buscar ([Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelectorFromConnectionStatus($status)) ([Windows.Devices.Bluetooth.BluetoothDevice])
$saida += Buscar ([Windows.Devices.Bluetooth.BluetoothLEDevice]::GetDeviceSelectorFromConnectionStatus($status)) ([Windows.Devices.Bluetooth.BluetoothLEDevice])

if ($saida.Count -gt 0) { ConvertTo-Json -InputObject @($saida) }
"""

# Lê a bateria que o Windows guarda para cada aparelho Bluetooth.
# O aparelho tem vários "nós" no Windows; procuramos em todos os que contêm o MAC.
PS_BATERIA = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$chave = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$macs = @(__MACS__)
$todos = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue
$saida = @()
foreach ($mac in $macs) {
    foreach ($d in ($todos | Where-Object { $_.InstanceId -like "*$mac*" })) {
        $p = Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName $chave -ErrorAction SilentlyContinue
        if ($p -and $null -ne $p.Data) {
            try {
                $valor = [int]$p.Data
                if ($valor -ge 0 -and $valor -le 100) {
                    $saida += [PSCustomObject]@{ Mac = $mac; Bateria = $valor; No = $no.InstanceId }
                    break
                }
            } catch { }
        }
    }
}
if ($saida.Count -gt 0) { ConvertTo-Json -InputObject @($saida) }
"""


def obter_baterias_windows(macs):
    """Retorna {mac: (porcentagem, aproximada)} para os aparelhos em que o Windows informa a bateria."""
    if not macs:
        return {}
    try:
        lista = ",".join(f"'{m}'" for m in macs)
        script = PS_BATERIA.replace("__MACS__", lista)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            creationflags=NO_WINDOW, capture_output=True, text=True,
            encoding="utf-8", errors="ignore", timeout=60
        )
        if DEBUG:
            print(f"[BT bateria] saída: {r.stdout.strip() or '(vazio)'} {r.stderr.strip()}")
        if r.stdout and r.stdout.strip():
            dados = json.loads(r.stdout)
            if isinstance(dados, dict):
                dados = [dados]
            # Valores vindos dos perfis de chamada (mãos-livres) são dados em 5 faixas: aproximados
            return {d["Mac"]: (int(d["Bateria"]), any(p in (d.get("No") or "").upper() for p in PERFIS_CHAMADA))
                    for d in dados}
    except Exception as e:
        print(f"Erro ao ler bateria: {e}")
    return {}


async def ler_baterias_ble(nomes):
    """Plano B: tenta ler a bateria pelo serviço padrão BLE. Retorna {nome: porcentagem}."""
    resultado = {}
    if not nomes:
        return resultado
    try:
        achados = await BleakScanner.discover(timeout=3.0)
    except Exception:
        return resultado
    for nome in nomes:
        for d in achados:
            if d.name and nome.lower() in d.name.lower():
                try:
                    async with BleakClient(d.address, timeout=3.0) as client:
                        valor = await client.read_gatt_char("00002a19-0000-1000-8000-00805f9b34fb")
                        resultado[nome] = valor[0]
                        break
                except Exception:
                    pass
    return resultado


async def obter_dispositivos_bluetooth():
    """Retorna apenas dispositivos Bluetooth CONECTADOS agora (não os apenas pareados)."""
    dispositivos = []

    try:
        resultado = subprocess.run(
            ["powershell", "-NoProfile", "-Command", PS_CONECTADOS],
            creationflags=NO_WINDOW, capture_output=True, text=True,
            encoding='utf-8', errors='ignore', timeout=60
        )

        if resultado.stderr and resultado.stderr.strip():
            # Se a consulta falhar, NÃO listamos nada (melhor que listar pareados por engano)
            print(f"Erro BT (PowerShell): {resultado.stderr.strip()}")

        if DEBUG:
            print(f"[BT] saída do Windows: {resultado.stdout.strip() or '(vazio)'}")

        if resultado.stdout.strip() == "RADIO_OFF":
            STATUS_BT["radio_ligado"] = False
            return []
        STATUS_BT["radio_ligado"] = True

        if resultado.stdout and resultado.stdout.strip():
            dados = json.loads(resultado.stdout)
            if isinstance(dados, dict):
                dados = [dados]

            vistos = set()
            for dev in dados:
                nome = dev.get("Name") or ""
                mac = (dev.get("Mac") or "").upper()
                if not nome or not mac or mac in vistos:
                    continue
                vistos.add(mac)
                dispositivos.append({
                    "nome": nome,
                    "fabricante": "Bluetooth",
                    "tipo_conexao": "Bluetooth",
                    "status": "Conectado",
                    "bateria": None,
                    "classe": "Bluetooth",
                    "id_sistema": mac
                })

            # Bateria 1: o que o Windows informa (todos de uma vez)
            baterias = obter_baterias_windows([d["id_sistema"] for d in dispositivos])
            for d in dispositivos:
                leitura = baterias.get(d["id_sistema"])
                d["bateria"], d["bateria_aprox"] = leitura if leitura else (None, False)

            # Bateria 2 (mais exata): serviço de bateria BLE.
            # Só para quem não tem valor ou tem valor aproximado, e nunca em celulares
            # (para não causar pedidos de pareamento no aparelho).
            agora = time.time()
            precisam = []
            for d in dispositivos:
                if d["bateria"] is not None and not d["bateria_aprox"]:
                    continue
                if any(p in d["nome"].lower() for p in PALAVRAS_CELULAR):
                    continue
                em_cache = CACHE_BLE.get(d["id_sistema"])
                if em_cache and agora - em_cache[1] < VALIDADE_BLE:
                    d["bateria"], d["bateria_aprox"] = em_cache[0], False
                    continue
                precisam.append(d)

            ble = await ler_baterias_ble([d["nome"] for d in precisam])
            for d in precisam:
                if d["nome"] in ble:
                    d["bateria"], d["bateria_aprox"] = ble[d["nome"]], False
                    CACHE_BLE[d["id_sistema"]] = (ble[d["nome"]], agora)

    except Exception as e:
        print(f"Erro BT: {e}")

    return dispositivos
