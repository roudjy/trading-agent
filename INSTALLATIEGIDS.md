# INSTALLATIEGIDS — JvR Trading Agent
## Van nul naar live in één avond

---

## STAP 1 — Accounts aanmaken (jij doet dit)

Doe dit in volgorde. Begin met IBKR want die duurt het langst.

### 1a. Interactive Brokers (stocks)
1. Ga naar **ibkr.com/nl**
2. Klik "Account openen"
3. Kies "Individueel account"
4. Upload paspoort + bewijs van adres
5. ⏳ Wacht 2-5 werkdagen op goedkeuring
6. Zodra goedgekeurd: noteer je **Account ID** (staat in de app)

### 1b. Bitvavo (Nederlandse crypto exchange)
1. Ga naar **bitvavo.com**
2. Maak account aan met je e-mailadres
3. Verifieer via iDIN of paspoort (snel, 5 minuten)
4. Ga naar Instellingen → API → Maak nieuwe API sleutel aan
5. Vink aan: **Lezen** en **Handelen** (NIET opnemen)
6. Noteer: **API Key** en **API Secret**

### 1c. Kraken (tweede crypto exchange)
1. Ga naar **kraken.com**
2. Maak account aan
3. Verificeer (Level 2 voor hogere limieten)
4. Ga naar Security → API → Create API Key
5. Rechten: **Query** + **Trade** (NIET withdraw)
6. Noteer: **API Key** en **Private Key**

### 1d. MetaMask (voor Polymarket)
1. Ga naar **metamask.io** → Download browser extensie
2. Maak nieuwe wallet aan
3. Schrijf je **12 woorden seed phrase OP PAPIER** → bewaar veilig
4. NOOIT digitaal opslaan, NOOIT delen
5. Noteer je **wallet adres** (begint met 0x...)

### 1e. Polymarket
1. Ga naar **polymarket.com**
2. Verbind je MetaMask wallet
3. Ga naar Settings → API Keys → Create Key
4. Noteer: **Private Key**, **API Key**, **Secret**, **Passphrase**

### 1f. Hetzner (VPS server)
1. Ga naar **hetzner.com**
2. Maak account aan
3. Ga naar Cloud → New Project → "trading-agent"
4. New Server:
   - Locatie: **Falkenstein** (Duitsland, dichtbij)
   - Image: **Ubuntu 24.04**
   - Type: **CX22** (€3,79/mnd)
   - SSH Key: maak aan (zie stap 2)
5. Noteer het **IP-adres** van je server (bijv. 65.21.xxx.xxx)

### 1g. Alchemy (blockchain RPC)
1. Ga naar **alchemy.com**
2. Maak gratis account aan
3. Create App → Netwerk: **Polygon Mainnet**
4. Noteer de **HTTPS URL** (bijv. https://polygon-mainnet.g.alchemy.com/v2/xxxxx)

### 1h. Anthropic API
1. Ga naar **console.anthropic.com**
2. Maak account aan (los van je claude.ai account)
3. Billing → Add $10 credit (genoeg voor maanden)
4. API Keys → Create Key
5. Noteer je **API Key** (begint met sk-ant-...)

---

## STAP 2 — VPS instellen (via Terminal op je Mac)

Open Terminal op je Mac (Spotlight → "Terminal")

### SSH sleutel aanmaken (eenmalig)
```bash
ssh-keygen -t ed25519 -C "jvr-trading-agent"
# Druk Enter op alle vragen (geen wachtwoord nodig)

# Kopieer je publieke sleutel (plak dit in Hetzner bij het aanmaken van de server)
cat ~/.ssh/id_ed25519.pub
```

### Verbinding maken met je VPS
```bash
# Vervang 65.21.xxx.xxx met jouw Hetzner IP
ssh root@65.21.xxx.xxx
```

### Server instellen (kopieer dit blok en plak in je VPS terminal)
```bash
# Update systeem
apt update && apt upgrade -y

# Installeer Docker
curl -fsSL https://get.docker.com | sh

# Installeer Git
apt install -y git

# Maak een gewone gebruiker aan (veiliger dan root)
useradd -m -s /bin/bash joery
usermod -aG docker joery
mkdir -p /home/joery/.ssh
cp ~/.ssh/authorized_keys /home/joery/.ssh/
chown -R joery:joery /home/joery/.ssh

# Schakel root SSH uit (veiligheid)
sed -i 's/PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config
systemctl restart sshd

echo "Server klaar!"
```

### Verbind voortaan als joery
```bash
ssh joery@65.21.xxx.xxx
```

---

## STAP 3 — Project uploaden naar VPS

Op je **Mac** (in Terminal):
```bash
# Ga naar de map waar je het project hebt opgeslagen
cd ~/Downloads/trading-agent   # of waar je het hebt

# Upload naar VPS (vervang IP)
scp -r . joery@65.21.xxx.xxx:/home/joery/trading-agent/

echo "Project geüpload!"
```

---

## STAP 4 — API Keys invullen

Verbind met je VPS:
```bash
ssh joery@65.21.xxx.xxx
cd trading-agent
```

Open de configuratie:
```bash
nano config/config.yaml
```

Vul in wat je hebt genoteerd in stap 1:
```yaml
exchanges:
  bitvavo:
    actief: true              # ← Verander naar true
    api_key: "jouw-key-hier"  # ← Invullen
    api_secret: "jouw-secret" # ← Invullen
    paper_trading: true       # ← Laat op true! (papier trading eerst)

  # ... rest van de exchanges
```

Sla op: `Ctrl+X` → `Y` → `Enter`

---

## STAP 5 — Agent starten

```bash
# Op je VPS, in de trading-agent map:
cd /home/joery/trading-agent

# Bouw de Docker containers (eerste keer duurt ~5 minuten)
docker compose build

# Start alles
docker compose up -d

# Controleer of alles draait
docker compose ps

# Bekijk de logs
docker compose logs -f agent
```

Je ziet nu zoiets als:
```
agent  | 2026-04-01 07:00:00 | INFO | Agent gestart: JvR Trading Agent
agent  | 2026-04-01 07:00:01 | INFO | Startkapitaal: €1000
agent  | 2026-04-01 07:00:02 | INFO | Paper trading modus actief
agent  | 2026-04-01 07:00:03 | INFO | Marktdata ophalen...
```

---

## STAP 6 — Dashboard bekijken

Open je browser op je Mac of iPhone:
```
http://65.21.xxx.xxx:8050
```
(vervang met jouw VPS IP)

Je ziet nu het dashboard met live data. Bookmark deze URL.

---

## STAP 7 — Paper trading fase (VERPLICHT, minimaal 4 weken)

De agent handelt nu met **nep geld**. Dit is bewust.

Wat je doet in deze fase:
1. Elke ochtend het dagrapport lezen (staat in het dashboard)
2. Controleren of de strategieën logisch handelen
3. Kijken of de bot-detectie werkt
4. Na 4 weken: evalueer of je tevreden bent met de resultaten

**Pas naar live als:**
- Win rate > 55% over minimaal 50 trades
- Geen crashes of rare gedragingen
- Je begrijpt waarom elke trade is gemaakt

---

## STAP 8 — Live zetten

Als je klaar bent voor live trading:
```bash
ssh joery@65.21.xxx.xxx
cd trading-agent
nano config/config.yaml
```

Verander voor elke exchange:
```yaml
paper_trading: false    # ← Verander naar false
```

Herstart:
```bash
docker compose restart agent
```

⚠️ Zorg dat je daadwerkelijk geld op de exchanges hebt gestort.

---

## Handige commando's voor later

```bash
# Logs bekijken
docker compose logs -f agent

# Agent herstarten
docker compose restart agent

# Alles stoppen
docker compose down

# Alles starten
docker compose up -d

# Agent status
docker compose ps

# Rapporten bekijken
ls reports/
cat reports/rapport_2026-04-01.md
```

---

## Problemen?

**Agent start niet:**
```bash
docker compose logs agent --tail=50
```

**Dashboard niet bereikbaar:**
```bash
# Controleer of poort 8050 open is
docker compose ps
# Controleer Hetzner Firewall: poort 8050 moet open zijn
```

**Trade wordt niet uitgevoerd:**
- Controleer of `paper_trading: true` staat (papier mode heeft geen echt geld nodig)
- Controleer API keys in config.yaml
- Bekijk logs: `docker compose logs agent`

---

## Veiligheid

- API keys staan ALLEEN in config.yaml op de VPS, nergens anders
- config.yaml staat NIET in Git (veilig)
- MetaMask seed phrase: papier in kluis, nergens digitaal
- VPS heeft alleen jouw SSH sleutel - geen wachtwoord login
- Nooit je private keys delen, ook niet met mij (Claude)
