"""
ESTUDO: como o app descobre a bateria de um fone/mouse Bluetooth no Windows
===========================================================================

Rode este arquivo sozinho para ver o resultado no terminal:

    python estudo_bateria.py

A ideia geral tem 3 etapas:

    1) Descobrir QUAIS aparelhos Bluetooth estão conectados agora   -> (nome + MAC)
    2) Para cada MAC, procurar no Windows a propriedade "bateria"   -> (porcentagem)
    3) Juntar tudo e mostrar

O Python NÃO fala direto com o Bluetooth. Ele chama o PowerShell (que já vem no
Windows), o PowerShell conversa com o Windows e devolve o resultado em JSON,
e o Python lê esse JSON. Esse "telefone sem fio" é a parte central da estrutura.

    Python  --(subprocess)-->  PowerShell  --(API do Windows)-->  Bluetooth
    Python  <--(JSON)---------  PowerShell  <------------------  resposta
"""

import json
import subprocess

# Evita a janela preta piscando quando virar .exe (não faz diferença no terminal)
NO_WINDOW = 0x08000000


# ----------------------------------------------------------------------------
# ETAPA 0: função auxiliar — roda um script PowerShell e devolve o JSON lido
# ----------------------------------------------------------------------------
def rodar_powershell(script, timeout=60):
    resultado = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,      # captura o que o PowerShell "imprime"
        text=True,                # devolve texto (não bytes)
        encoding="utf-8",
        errors="ignore",
        timeout=timeout,          # nunca deixa travar para sempre
        creationflags=NO_WINDOW,
    )
    saida = resultado.stdout.strip()
    if not saida:
        return []                 # o PowerShell não achou nada
    dados = json.loads(saida)
    # O PowerShell devolve um objeto (dict) quando há 1 item e uma lista quando há vários.
    # Padronizamos: sempre devolvemos lista.
    return [dados] if isinstance(dados, dict) else dados


# ----------------------------------------------------------------------------
# ETAPA 1: quais aparelhos Bluetooth estão CONECTADOS agora?
# ----------------------------------------------------------------------------
# Usamos a API do Windows (WinRT) que a própria tela "Bluetooth e dispositivos"
# usa. Ela aceita um "seletor" que filtra pelo status = Connected.
# O PowerShell não "espera" sozinho essas chamadas assíncronas, por isso existe
# a função Await() abaixo (é um truque conhecido, pode copiar sem medo).
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

$conectado = [Windows.Devices.Bluetooth.BluetoothConnectionStatus]::Connected

# Dois tipos de Bluetooth: o "clássico" (fones, caixas) e o LE (mouses, teclados modernos)
$seletores = @(
    [Windows.Devices.Bluetooth.BluetoothDevice]::GetDeviceSelectorFromConnectionStatus($conectado),
    [Windows.Devices.Bluetooth.BluetoothLEDevice]::GetDeviceSelectorFromConnectionStatus($conectado)
)

$saida = @()
foreach ($seletor in $seletores) {
    $achados = Await ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($seletor)) ([Windows.Devices.Enumeration.DeviceInformationCollection])
    foreach ($d in $achados) {
        # O Id termina com o endereço MAC (ex.: ...-aa:bb:cc:dd:ee:ff). Tiramos os ":"
        $mac = $d.Id.Substring($d.Id.LastIndexOf('-') + 1).Replace(':', '').ToUpper()
        $saida += [PSCustomObject]@{ Name = $d.Name; Mac = $mac }
    }
}
if ($saida.Count -gt 0) { ConvertTo-Json -InputObject @($saida) }
"""


# ----------------------------------------------------------------------------
# ETAPA 2: a bateria
# ----------------------------------------------------------------------------
# O Windows guarda a bateria como uma "propriedade" do aparelho, identificada por
#   {104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2      (nome oficial: DEVPKEY_Bluetooth_Battery)
#
# PONTO IMPORTANTE (foi o que fez funcionar):
# Um mesmo fone aparece no Windows como VÁRIOS "nós" (um para o aparelho, outros
# para cada serviço: áudio, mãos-livres, etc.), e o ID de cada nó é diferente.
# A bateria pode estar em QUALQUER um deles. O que todos têm em comum é o MAC
# dentro do ID. Então fazemos:
#
#     para cada MAC:
#         para cada nó cujo ID CONTÉM o MAC:
#             tenta ler a bateria; se achou, para.
#
# (Antes eu procurava por um ID "completo" que na verdade não existe, por isso
#  a bateria nunca aparecia.)
PS_BATERIA = r"""
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$chave = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'
$macs = @(__MACS__)

# Lista todos os dispositivos presentes UMA vez só (é lento; não repita dentro do laço)
$todos = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue

$saida = @()
foreach ($mac in $macs) {
    foreach ($no in ($todos | Where-Object { $_.InstanceId -like "*$mac*" })) {
        $p = Get-PnpDeviceProperty -InstanceId $no.InstanceId -KeyName $chave -ErrorAction SilentlyContinue
        if ($p -and $null -ne $p.Data) {
            try {
                $valor = [int]$p.Data
                if ($valor -ge 0 -and $valor -le 100) {      # valida: bateria é de 0 a 100
                    $saida += [PSCustomObject]@{ Mac = $mac; Bateria = $valor }
                    break                                    # achou: não precisa olhar os outros nós
                }
            } catch { }
        }
    }
}
if ($saida.Count -gt 0) { ConvertTo-Json -InputObject @($saida) }
"""


def ler_baterias(macs):
    """Recebe uma lista de MACs e devolve {mac: porcentagem}."""
    if not macs:
        return {}
    # Troca o marcador __MACS__ pela lista real:  'AABBCC...','112233...'
    lista_ps = ",".join(f"'{m}'" for m in macs)
    script = PS_BATERIA.replace("__MACS__", lista_ps)
    dados = rodar_powershell(script)
    return {item["Mac"]: int(item["Bateria"]) for item in dados}


# ----------------------------------------------------------------------------
# ETAPA 3: juntar tudo
# ----------------------------------------------------------------------------
def main():
    print("Procurando aparelhos Bluetooth conectados...\n")
    aparelhos = rodar_powershell(PS_CONECTADOS)

    if not aparelhos:
        print("Nenhum aparelho Bluetooth conectado agora.")
        return

    baterias = ler_baterias([a["Mac"] for a in aparelhos])

    for a in aparelhos:
        bateria = baterias.get(a["Mac"])
        texto = f"{bateria}%" if bateria is not None else "não informada pelo aparelho"
        print(f"  {a['Name']:<30} MAC {a['Mac']}   bateria: {texto}")


if __name__ == "__main__":
    main()

# ----------------------------------------------------------------------------
# PARA ESTUDAR / EXPERIMENTAR
# ----------------------------------------------------------------------------
# 1) Troque o `print` da função rodar_powershell para ver o JSON cru que volta.
# 2) Se um aparelho mostra "não informada", ele provavelmente não envia a bateria
#    ao Windows (isso depende do fabricante). O app tem um "plano B" (bleak) que
#    tenta ler pelo serviço padrão BLE, em utils/bluetooth_monitor.py.
# 3) Para ver todos os nós de um aparelho no PowerShell, rode (trocando o MAC):
#       Get-PnpDevice -PresentOnly | ? { $_.InstanceId -like '*AABBCCDDEEFF*' }
