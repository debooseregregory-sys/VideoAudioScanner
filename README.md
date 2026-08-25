# VideoAudioScanner

Een Windows/Python desktopapplicatie om video- en audiobestanden te scannen met **FFprobe**. De app toont per bestand onder andere duur, resolutie, video-/audiocodec, bestandsgrootte en fouten, en kan de resultaten naar CSV exporteren.

## Functies

- Donkere PySide6-interface
- Recursief scannen van een gekozen map
- Video- en audioformaten herkennen
- FFprobe automatisch detecteren via PATH en enkele standaard Windows-locaties
- Scan op de achtergrond zodat de interface blijft reageren
- Stoppen van een lopende scan
- Live scanresultaten in een tabel
- CSV-export met UTF-8 BOM voor goede Excel-ondersteuning
- Per bestand duidelijke foutstatus wanneer FFprobe het bestand niet kan lezen
- GitHub Actions build voor Windows `.exe`

## Vereisten

- Windows 10/11
- Python 3.11+ voor ontwikkeling
- FFmpeg/FFprobe

### FFmpeg installeren

Installeer een recente Windows-build van FFmpeg en zorg dat de map met `ffprobe.exe` in `PATH` staat. De applicatie probeert daarnaast enkele standaardlocaties onder `Program Files`.

Controleer in PowerShell:

```powershell
ffprobe -version
```

## Lokaal starten

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python main.py
```

## Gebruik

1. Kies **Bladeren…** en selecteer een hoofdmap.
2. Klik **Scan starten**.
3. Wacht tot de bestanden in de tabel verschijnen.
4. Klik **CSV exporteren** om de resultaten op te slaan.

## CSV-kolommen

De export bevat het volledige pad, bestandsnaam, media type, duur, resolutie, codecs, bestandsgrootte en status.

## Windows EXE

Bij een push naar `main` wordt via GitHub Actions automatisch een Windows-build gemaakt met PyInstaller. Het resultaat wordt als workflow-artifact gepubliceerd.

## Projectstructuur

```text
VideoAudioScanner/
├── .github/
│   └── workflows/
│       └── build-windows.yml
├── main.py
├── scanner.py
├── requirements.txt
└── README.md
```

## Opmerking over FFmpeg in de EXE

PyInstaller bundelt de Python-app, maar FFmpeg/FFprobe zelf wordt niet zonder licentie-/distributiekeuze meegeleverd. De gebruiker moet FFprobe daarom beschikbaar maken op het systeem, tenzij later een expliciete FFmpeg-distributiestrategie wordt toegevoegd.
