# Flash gratuit d'un téléphone SC9863A via CVE-2022-38694

Procédure complète, testée et fonctionnelle, pour re-flasher un smartphone basé sur le chipset **Unisoc / Spreadtrum SC9863A** (`s9863a1h10_go` et variantes) **sans payer** pour les outils Windows commerciaux (SPD Flash Tool payant, HalabTech, FirmwareWorld, etc.) et **sans payer** pour le firmware.

Méthode testée avec succès sur un **Philips S6210T (Essence 12)** complètement mort ("OS not found"), ressuscité en version boot propre. La procédure s'applique à **tous les smartphones SC9863A** :

- Philips S6210 / S6210T / S6211 / S6311
- itel V654L / Vision 3
- Villaon V50s / V651L
- Hisense HLTE229
- Nokia C3
- Realme C11 2021 (RMX3231) / Narzo 50i (RMX3235)
- ZTE Blade A31 / A51 / A52 / A5_2019 / A7_2019 / v2020_smart / Voyage 40se
- Vankyo S30, FOXXD A67L, Welcome C37 Ultra, Infinix Smart 6, etc.

> ⚠️ **Avertissement** : flasher un téléphone est destructif. Risque de brick réel si la manipulation est mal faite ou si l'alimentation est interrompue. Ce projet est fourni "AS IS", sans aucune garantie. À utiliser à vos propres risques et pour vos propres appareils uniquement.

---

## Pourquoi cette méthode fonctionne

Les smartphones SC9863A récents ont un **FDL2 signé en read-only** : l'outil officiel Spreadtrum (`SPD Research Tool`) refuse d'écrire sur la flash via le FDL stock. La CVE-2022-38694 (découverte par NCC Group) permet de contourner la vérification de signature du BootROM en exploitant un stack overflow, et ainsi de charger un FDL "download mode" non-signé qui accepte les écritures.

Ce projet :
1. **Ne contient aucun binaire propriétaire** (ni firmware, ni FDL, ni shellcode). Tout est téléchargé depuis des sources publiques listées.
2. **Fournit un script Python** qui parse le XML du firmware et génère la séquence complète de commandes `spd_dump` pour un flash complet (repartition, write_part × N, erase_part × N) avec préservation de l'IMEI et de la calibration radio.
3. **Gère le resume** si le FDL2 crashe en cours de flash (cas fréquent avec les gros firmwares type `super.img` > 3 GB).

---

## Prérequis

- Linux (testé sur Kali/Debian — fonctionne sur toute distro récente)
- Paquets : `git make gcc libusb-1.0-0-dev python3 unzip wget` (minimum)
- Un câble USB **data** fiable (pas un câble charge-only)
- Un peu de patience

---

## Étape 1 — Installer les outils

```bash
# Dépendances
sudo apt update
sudo apt install -y git make gcc libusb-1.0-0-dev python3 unzip wget

# spd_dump (fork TomKing avec support CVE)
git clone https://github.com/TomKing062/spreadtrum_flash.git
cd spreadtrum_flash && make && cd ..

# unpac (ilyakurdyukov) — pour extraire les partitions du .pac
git clone https://github.com/ilyakurdyukov/spreadtrum_flash.git ilya_sprd
cd ilya_sprd/unpac && make && cd ../..
```

## Étape 2 — Règle udev (évite sudo pour spd_dump)

```bash
sudo cp udev/80-spreadtrum.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Étape 3 — Récupérer le firmware stock (`.pac`)

Compte gratuit sur [Needrom.com](https://www.needrom.com/) (1 download/jour). Cherche le modèle exact du téléphone. Si rien, cherche par **platform code** (visible dans le nom de fichier d'autres firmwares du même constructeur). Pour tous les SC9863A, le code platform contient souvent `A605-V-OP` ou `F069MJa`.

Extrais le `.zip` → tu dois obtenir un fichier `*.pac` de 2-4 GB.

**Astuce** : si le nom de la page Needrom indique un modèle proche (ex : "S6210 Essence 10"), regarde la description — le `.pac` à l'intérieur peut être celui de ton modèle exact (ex : `S6210T-A605-V-OP-V018.pac`). Confirme avec :

```bash
./ilya_sprd/unpac/unpac list /chemin/vers/firmware.pac | head -5
```

## Étape 4 — Récupérer les outils d'exploit (FDL unlocked + shellcode)

Télécharge depuis les [Releases de TomKing062/CVE-2022-38694_unlock_bootloader](https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader/releases/latest) **n'importe quel pack SC9863A**. Le plus simple : `sc9863a_Itel_Vision_3.zip` (1.2 MB).

```bash
mkdir exploit && cd exploit
wget "https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader/releases/download/1.72/sc9863a_Itel_Vision_3.zip"
unzip sc9863a_Itel_Vision_3.zip
cd ..
```

Tu as besoin de 3 fichiers de ce pack :
- `fdl1-dl.bin` (~52 KB)
- `fdl2-dl.bin` (~700 KB)
- `custom_exec_no_verify_4ee8.bin` (128 B) — le shellcode CVE

## Étape 5 — Extraire les partitions du firmware

```bash
mkdir extracted_pac
./ilya_sprd/unpac/unpac -d extracted_pac extract /chemin/vers/firmware.pac
```

Tu dois obtenir ~35 fichiers (`.img`, `.bin`, `.xml`).

## Étape 6 — Configurer le générateur de script

Édite `scripts/build_flash_cmd.py` et ajuste les chemins au début :

```python
PAC = "/chemin/vers/firmware.pac"
XML = "/chemin/vers/extracted_pac/s9863a1h10_go.xml"   # le .xml extrait du .pac
OUT_DIR = "/chemin/vers/extracted_pac"
FDL1 = "/chemin/vers/exploit/fdl1-dl.bin"
FDL2 = "/chemin/vers/exploit/fdl2-dl.bin"
UNPAC = "/chemin/vers/ilya_sprd/unpac/unpac"
SPD_DUMP = "/chemin/vers/spreadtrum_flash/spd_dump"
```

Puis génère le script :

```bash
python3 scripts/build_flash_cmd.py
# → /tmp/flash_cmd.sh prêt à l'emploi
```

## Étape 7 — Entrer en BROM "fresh" (étape la plus importante)

Le BROM SC9863A a un **idle timeout d'environ 2 minutes**. Si tu mets trop longtemps à lancer `spd_dump`, le BROM devient inerte (visible en USB mais refuse les commandes). Il faut un timing serré.

Protocole obligatoire :

1. Débranche l'USB du téléphone
2. Appuie et maintiens **Power + Volume Bas ensemble** pendant **15 secondes** (force off, même si figé)
3. Relâche. Attends 5 secondes.
4. Appuie et maintiens **Volume Bas** (seul)
5. **Branche l'USB** en gardant Volume Bas appuyé
6. Garde Volume Bas appuyé **10 secondes** après le branchement
7. **Dans les 30 secondes qui suivent**, lance la commande de flash

**Comment vérifier que le BROM est bien en mode "fresh"** :

```bash
dmesg | tail -5
# Tu dois voir :
# usb 1-X: new high-speed USB device
# usb 1-X: idVendor=1782, idProduct=4d00, bcdDevice= 2.02
# usb 1-X: New USB device strings: Mfr=0, Product=0, SerialNumber=0
```

Les signes d'un vrai BROM fresh :
- `bcdDevice= 2.02` (et PAS `24.16`)
- `Mfr=0 Product=0` (strings vides)
- `high-speed` (pas `full-speed`)

Si tu vois `Mfr=1 Product=2 ... Sprd Gadget Serial / spreadtrum with musb-hdrc` → c'est le bootloader secondaire, PAS le BROM. Refais la manip.

## Étape 8 — Lancer le flash

Depuis le dossier qui contient `custom_exec_no_verify_4ee8.bin` (spd_dump le cherche dans le cwd) :

```bash
cd /chemin/vers/exploit
(yes yes; sleep 10000) | bash /tmp/flash_cmd.sh 2>&1 | tee /tmp/flash.log
```

Le `yes yes` répond automatiquement aux confirmations interactives de `spd_dump`.

**Événements à surveiller dans le log** :
- `BSL_REP_VER: "SPRD3\0"` → BootROM OK
- `EXEC FDL1` puis `EXEC FDL2` → FDLs chargés
- `FDL2: incompatible partition` → **NORMAL**, c'est juste le message avertissant que la partition table actuelle ne matche pas
- `Write Part Done: <partition>` ou `Force Write <partition> Done` → chaque partition écrite avec succès
- `Erase Part Done: <partition>` → effacement OK

Vitesse typique : **~40-45 MB/s**. Le flash complet prend **10-15 min** si tout va bien d'un coup.

## Étape 9 — Gérer les crashs du FDL2 (si ça arrive)

Le FDL2 "download mode" d'Itel/ZTE/autres n'est pas super stable sur du long run. Il peut crasher après 5-15 writes consécutifs, ou au milieu d'un gros fichier (ex : `super.img` à 7 %).

**Signes** : le log affiche `usb_send failed : LIBUSB_ERROR_TIMEOUT` et le processus `spd_dump` meurt.

**Solution — Resume** :

1. Note les partitions déjà faites (grep `Done` dans le log)
2. Ajoute-les à la liste `ALREADY_WRITTEN` dans `build_flash_cmd.py`
3. Refais la manip BROM fresh (Étape 7)
4. Regénère et relance le script (Étape 6 + 8)

**Pour `super.img` (3-4 GB) qui crashe souvent** : utilise `scripts/flash_super.sh.template` qui le flashe en isolation (une seule write dans une session FDL2 "fraîche"). Chez nous il est passé en 76 sec à 44 MB/s.

## Étape 10 — Test

1. Débranche l'USB
2. Appui long Power (~5 sec)
3. Attends 5-10 min au premier boot (initialisation complète Android)
4. → Écran de setup initial Android = **succès** 🎉

---

## Pourquoi préserver `prodnv` et `l_fixnv1_a`

Le script **saute volontairement** 5 partitions :
- `prodnv` → contient IMEI, SN, MAC Wi-Fi/BT, données usine uniques
- `l_fixnv1_a`, `l_fixnv1_b`, `l_fixnv2_a`, `l_fixnv2_b` → calibration radio LTE spécifique au hardware

Les flasher avec les images stock du `.pac` écraserait ton IMEI par celui par défaut du firmware (souvent null ou de fabrique) → ton phone ne fonctionnerait plus avec les cartes SIM. Les sites payants (HalabTech, FirmwareWorld) utilisent les mêmes astuces — notre script les préserve par défaut.

---

## Sources et crédits

- **CVE-2022-38694** → [recherche NCC Group](https://research.nccgroup.com/2022/09/02/theres-another-hole-in-your-soc-unisoc-rom-vulnerabilities/)
- **spd_dump (fork actif)** → [TomKing062/spreadtrum_flash](https://github.com/TomKing062/spreadtrum_flash)
- **Exploit kit SC9863A + FDLs unlocked** → [TomKing062/CVE-2022-38694_unlock_bootloader](https://github.com/TomKing062/CVE-2022-38694_unlock_bootloader)
- **spd_dump original + unpac** → [ilyakurdyukov/spreadtrum_flash](https://github.com/ilyakurdyukov/spreadtrum_flash)
- **Signcheck bypass (lecture avancée)** → [TomKing062/unisoc_chipram_signcheck_exploit](https://github.com/TomKing062/unisoc_chipram_signcheck_exploit)
- Firmware stock → [Needrom.com](https://www.needrom.com/) (compte gratuit)

---

## Licence

MIT. Voir [LICENSE](LICENSE).

Les outils tiers référencés ci-dessus ont leurs propres licences (GPL-2, GPL-3, etc.) — respecte-les si tu redistribues.
