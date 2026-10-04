# Corsair Dark Core RGB Pro — solución al emparejamiento Bluetooth (Linux)

El Corsair Dark Core RGB Pro no se emparejaba por Bluetooth: aparecía en el
escaneo, conectaba un momento y el emparejamiento fallaba. Este repositorio
documenta la causa, encontrada con una captura de paquetes, y la solución.

**Resumen:** el ratón dice soportar la velocidad Bluetooth LE **2M PHY**, pero la
conexión se queda colgada cuando el adaptador tiene 2M activado. Limitando el
adaptador a **1M PHY**, el emparejamiento termina en un segundo y el ratón
reconecta solo después.

English: [README.md](README.md) · Para agentes de IA: [AGENTS.md](AGENTS.md)

## Síntomas

- El ratón aparece en el escaneo como `DARK CORE RGB PRO`.
- `bluetoothctl pair` falla con `org.bluez.Error.AuthenticationCanceled` a los 30 segundos.
- `bluetoothctl connect` (sin emparejar) conecta y se cae a los pocos segundos.
- El menú Bluetooth del escritorio muestra "falló el emparejamiento" o conecta y desconecta en bucle.
- El receptor 2.4 GHz (Slipstream) y el cable USB funcionan bien.

## Solución rápida

```sh
git clone https://github.com/Carlos12001/corsair-dark-core-rgb-pro-bluetooth-fix.git
cd corsair-dark-core-rgb-pro-bluetooth-fix
sudo ./install.sh
```

Después empareja el ratón:

1. Apaga el ratón (interruptor de abajo).
2. Mantén apretado el botón de perfil (el que está detrás de la rueda).
3. Sin soltarlo, mueve el interruptor a **BT**. Suéltalo cuando la lucecita entre
   la rueda y el botón de perfil parpadee en azul.
4. Emparéjalo desde el menú Bluetooth de tu escritorio, o con:

   ```sh
   bluetoothctl --timeout 15 scan le
   bluetoothctl devices | grep -i "dark core"     # anota la dirección
   bluetoothctl pair  AA:BB:CC:DD:EE:FF
   bluetoothctl trust AA:BB:CC:DD:EE:FF
   ```

Para deshacer todo: `sudo ./uninstall.sh`.

## Probar a mano primero (sin instalar nada)

Esto es toda la solución. Dura hasta que apagues y enciendas el Bluetooth:

```sh
sudo btmgmt phy                 # mira "Selected phys": incluye LE2MTX LE2MRX
sudo btmgmt phy BR1M1SLOT BR1M3SLOT BR1M5SLOT EDR2M1SLOT EDR2M3SLOT EDR2M5SLOT \
                EDR3M1SLOT EDR3M3SLOT EDR3M5SLOT LE1MTX LE1MRX
sudo btmgmt phy                 # "Selected phys" debe terminar en: LE1MTX LE1MRX
```

La lista conserva todos los tipos de paquete de Bluetooth clásico (BR/EDR) y solo
quita `LE2MTX LE2MRX LECODEDTX LECODEDRX`. Si la línea "Supported phys" de tu
adaptador es distinta, pasa su propia lista sin esos cuatro.

Ahora pon el ratón en modo emparejamiento y emparéjalo. Si funciona, instala el
servicio para que el ajuste sea permanente.

## Qué hace el instalador

| Archivo | Se instala en | Para qué |
|---|---|---|
| `bt-le-1m-phy` | `/usr/local/bin/` | Aplica el comando `btmgmt phy` de arriba y vigila BlueZ por D-Bus para volver a aplicarlo cada vez que el adaptador se enciende |
| `bt-le-1m-phy.service` | `/etc/systemd/system/` | Arranca el script junto con `bluetooth.target` |

El servicio hace falta porque el kernel de Linux vuelve a activar 2M y Coded PHY
cada vez que el adaptador se enciende (arranque, apagar/encender Bluetooth, modo avión).

Requisitos: BlueZ con `btmgmt`, `dbus-monitor`, systemd.

## Causa

La captura con `btmon` del emparejamiento fallido muestra esta secuencia
([extracto completo](docs/btmon-failing-2m-phy.txt)):

1. La conexión LE se crea bien.
2. El emparejamiento SMP corre normal: petición, respuesta (legacy, Just Works) e
   intercambio de valores Confirm y Random en ambos sentidos.
3. El PC envía `LE Start Encryption` y el adaptador acepta el comando.
4. **Nunca llega el evento `Encryption Change`.** La conexión sigue viva, pero el
   cifrado no arranca. Un `LE Connection Update` posterior tampoco se completa.
5. A los 30 segundos vence el temporizador SMP de BlueZ, desconecta con
   "Authentication Failure" y el usuario ve `AuthenticationCanceled`.

Con una conexión simple sin emparejar, el enlace quedó en silencio unos 0,7
segundos después de conectar y murió con "Connection Timeout".

Con el adaptador limitado a 1M, la misma secuencia se completa
([extracto completo](docs/btmon-working-1m-phy.txt)): `Encryption Change: Enabled
with AES-CCM` llega 42 ms después de `LE Start Encryption`, se reparten las claves
y el servicio HID queda activo.

### Qué está comprobado y qué es deducción

- **Comprobado en este equipo:** el emparejamiento falla siempre con 2M PHY
  seleccionado en el adaptador (tres intentos capturados) y funcionó al primer
  intento con solo 1M. La reconexión tras apagar y encender el adaptador también
  funciona con solo 1M.
- **Deducido:** que un cambio a 2M PHY se queda colgado en la capa de enlace y
  bloquea el cifrado que va en cola detrás. Las capturas HCI no muestran los
  paquetes de la capa de enlace, así que no se puede decir si el que se cuelga es
  el ratón o el adaptador. Haría falta un sniffer de radio para confirmarlo.
- **Descartado:** el intervalo de conexión (7,5 ms y 30–50 ms fallaron igual con
  2M) y el orden de los pasos (conectar y luego emparejar, o emparejar directo).

## Equipo de prueba

| | |
|---|---|
| Ratón | Corsair Dark Core RGB Pro, versión HID Bluetooth 5.00 |
| Laptop | ASUS TUF Dash F15 FX517ZC |
| Adaptador Bluetooth | Intel AX201 (USB `8087:0026`), firmware `ibt-0040-4150` |
| Sistema | CachyOS (basado en Arch), kernel 7.2.8 |
| BlueZ | 5.87 |
| Fecha | 2026-10-03 |

A tener en cuenta sobre esta prueba:

- Un solo ratón y un solo adaptador. Otros adaptadores pueden no necesitar el
  arreglo, o necesitarlo también.
- `ConnectionSupervisionTimeout=600` ya estaba puesto en `[LE]` de
  `/etc/bluetooth/main.conf` por un intento anterior. No se volvió a probar sin él.
- El primer emparejamiento exitoso se hizo con intervalo de conexión de 7,5 ms
  puesto por debugfs. La reconexión con el intervalo normal (30–50 ms) funciona;
  un emparejamiento nuevo con el intervalo normal no se probó aparte.
- Al escribir esto no se había probado un reinicio completo, solo apagar y
  encender el adaptador.
- El mismo ratón tampoco emparejaba en Windows en esta laptop. Es probable que la
  causa sea la misma, pero no se ha probado.

## Efectos secundarios

Todos los dispositivos Bluetooth LE de este adaptador usan 1M. En ratones,
teclados y mandos no se nota. Los dispositivos que aprovechan 2M (auriculares LE
Audio) tienen menos ancho de banda. El Bluetooth clásico (la mayoría de
auriculares y altavoces) no cambia.

## Si algo falla

```sh
systemctl status bt-le-1m-phy          # debe estar activo
sudo btmgmt phy | grep ^Selected       # no debe contener LE2M ni LECODED
bluetoothctl info AA:BB:CC:DD:EE:FF    # Paired / Bonded / Trusted / Connected
```

- **El ratón no aparece en el escaneo.** No está en modo emparejamiento. Solo se
  anuncia a equipos nuevos si lo enciendes en BT con el botón de perfil apretado.
- **Lo emparejaste antes del arreglo y ahora va mal.** Quítalo y empareja de
  nuevo: `bluetoothctl remove AA:BB:CC:DD:EE:FF`.
- **Sigue fallando.** Captura el intento y compáralo con los extractos de `docs/`:

  ```sh
  sudo btmon -w /tmp/mouse.snoop        # terminal 1, Ctrl+C al terminar
  python3 tools/bt_pair_test.py         # terminal 2, ratón en modo emparejamiento
  btmon -r /tmp/mouse.snoop | less
  ```

## Licencia

MIT. Ver [LICENSE](LICENSE).
