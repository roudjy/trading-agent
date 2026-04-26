# Quant Research Engine — Roadmap v3 (post‑v3.15, through v3.17)

## Doel van dit document

Dit document vervangt eerdere roadmapversies als **actueel startpunt voor nieuwe sessies**.  
Het document is geschreven om:

1. de **huidige systeemstaat** na v3.15 vast te leggen  
2. de **architectuurregels** scherp te houden  
3. de **bouwvolgorde t/m v3.17** ondubbelzinnig te maken  
4. de **business-/throughput-logica** expliciet toe te voegen  
5. nieuwe sessies met Claude/Codex direct te kunnen voeden zonder interpretatieruimte

Dit document is bedoeld voor gebruik naast:

- `AGENTS.md`
- `CLAUDE.md`
- `orchestrator_brief.md`
- `qre_prompt_guidelines.md`

---

# 1. Executive summary

De Quant Research Engine is niet langer een losse backtest-tool, maar een **deterministisch, artifact-driven, preset-gedreven research platform** met:

- Research Quality Engine
- Candidate Promotion Framework
- Regime Intelligence & Gating
- Portfolio / Sleeve Research
- Paper Validation Engine
- React frontend + Flask control surface
- Scheduler op VPS
- Docker deployment naar productie

De kernregel blijft leidend:

> **De engine is een alpha-filter, geen alpha-generator.**

De machine is bedoeld om:

- slechte hypotheses snel af te wijzen
- false positives te onderdrukken
- alleen statistisch, operationeel en execution-technisch verdedigbare candidates door te laten

De belangrijkste verschuiving vanaf nu is:

> **niet meer “meer strategieën”, maar een slimmere, autonomere, throughput-gedreven research machine bouwen die zonder handmatige campagnekeuzes werkt en pas daarna richting shadow/live gaat.**

---

# 2. Huidige state (na v3.15)

## 2.1 Wat nu live en gebouwd is

Voltooid en live:

- **v3.11 — Research Quality Engine**
- **v3.12 — Candidate Promotion Framework**
- **v3.13 — Regime Intelligence & Gating**
- **v3.14 — Portfolio / Sleeve Research**
- **v3.15 — Paper Validation Engine**

### Huidige systeemeigenschappen

Het systeem is nu:

- deterministisch
- reproduceerbaar
- artifact-driven
- preset-gedreven
- walk-forward / OOS enforced
- PSR / DSR aware
- candidate lifecycle aware
- regime-aware
- portfolio/sleeve-aware
- paper-validation aware
- observeerbaar via artifacts + dashboard
- bedienbaar via UI/API/CLI
- daily-scheduler ready

## 2.2 Wat het systeem nog niet is

Het systeem is nog **niet**:

- een no-touch research operating system
- een high-throughput campaign factory
- een shadow trading system
- een broker-integrated live trading platform
- een gecontroleerd live capital deployment system

## 2.3 Wat recente live runs inhoudelijk hebben geleerd

Recente live campagnes hebben aangetoond:

- de pipeline is technisch gezond
- v3.14.1 runtime hotfixes werken
- v3.15 is live
- de huidige enabled preset-catalogus levert nog **geen robuuste candidate**
- failure modes zijn inhoudelijk, niet technisch:
  - `insufficient_trades`
  - `screening_criteria_not_met`
- degenerate/no-survivor flows laten public latest artifacts stale staan
- `pairs_equities_daily_baseline` is nog steeds het enige mathematisch andere preset-pad dat niet inhoudelijk is getoetst

### Belangrijkste interpretatie

De engine doet nu wat hij moet doen:

- niets promoveren “omdat er iets uit moet komen”
- zwakke hypotheses vroeg afwijzen
- paper alleen bereiken als er echte survivors zijn

Dat is een succes van de filter, niet een mislukking van de machine.

---

# 3. Kernprincipes (blijven hard)

## 3.1 North star

> **De research engine is geen alpha-generator maar een alpha-filter.**

Het systeem moet niet de hoogste backtest-Sharpe vinden, maar de strategieën identificeren die:

- robuust zijn
- statistisch verdedigbaar zijn
- uitvoerbaar zijn
- standhouden out-of-sample
- niet afhankelijk zijn van één parameterpunt, één asset of één regime

## 3.2 Architectuurregels

Deze regels zijn hard:

- `registry.py` = single source of truth voor strategy registration
- `research/run_research.py` = centrale orchestrator
- artifacts = source of truth
- frontend = UI only
- backend = control surface
- engine = research logic

## 3.3 Frozen contracts

Deze mogen niet breken:

- `research_latest.json`
- `strategy_matrix.csv`

Nieuwe informatie hoort in **adjacent artifacts**, niet door bestaande public contracts stil te muteren.

## 3.4 Research discipline

- focus op hypothesevorming en falsificatie
- geen brute-force parameter searches
- geen strategy explosion
- negatieve resultaten bewaren
- eenvoud boven complexiteit
- trend blijft hoofdpad
- mean reversion voor crypto intraday blijft diagnostisch, niet primary alpha path

## 3.5 Automation discipline

Nieuwe leidende regel:

> **Campaign-selectie, campaign-enqueueing en standaard follow-up moeten 100% autonoom worden.**

De operator mag alleen:

- campagnecatalogus bekijken
- policy-tiering begrijpen
- resultaten lezen
- expliciete governance-beslissingen nemen
- stop/go op hoger niveau bepalen

De operator mag **niet** de volgende run handmatig hoeven kiezen.

---

# 4. Het echte ontbrekende stuk

## 4.1 Wat níet meer de primaire bottleneck is

Niet primair:
- UI
- basic orchestration
- paper-layer existence
- simpele scheduler
- losse research runs

## 4.2 Wat wél de primaire bottleneck is

De bottleneck is nu:

- te weinig **throughput**
- te veel **operator-latency**
- te weinig **cross-run intelligence**
- te weinig **failure-memory als actieve policy**
- te weinig **autonome campagnekeuze**
- te weinig **compute-budget discipline**

### In gewone taal

Je mist niet nog een backtestlaag.  
Je mist nu vooral een **research operating system** dat zelfstandig bepaalt:

- welke campagne nu het meeste informatie oplevert
- welke paden structureel dood zijn
- welke survivors follow-up verdienen
- welke runs cooldown nodig hebben
- wanneer paper/shadow economisch zinvol is

---

# 5. Businesskader (mei / juni)

## 5.1 Budget-aanname

Aangenomen:

- extra run-budget start in **mei**
- **mei: €200 extra**
- **juni: €300 extra**

Niet voor “meer runs om meer runs”, maar voor:

> **queue discipline → hogere campaign throughput → candidate → paper-worthy candidate → shadow → gecontroleerd live**

## 5.2 Wat het budget moet kopen

Dit budget moet niet vooral compute kopen, maar:

1. autonome campaign-operatie
2. meer meaningful campaigns
3. sneller falsifiëren
4. survivors sneller escaleren
5. eerder hard kunnen beslissen of doorgaan rationeel is

## 5.3 Kill gate

Belangrijke zakelijke gate:

> Als na mei + juni, met verhoogde throughput en autonome campaign-selectie, nog steeds **0 paper-worthy candidates** overblijven en dezelfde failure modes terugkeren, dan is de huidige hypothesis space waarschijnlijk commercieel te zwak.

Dus:
- extra budget is een **discovery sprint**
- geen open-einde investering
- geen blind vertrouwen op “meer compute lost het op”

---

# 6. Waarom v2 niet meer genoeg is

Roadmap v2 is sterk, maar nog niet hard genoeg op het nieuwe knelpunt.

Wat v2 nog onvoldoende first-class maakt:

- autonomous campaign policy
- longitudinal evidence
- compute budget allocator
- worker lease/admission control
- economics dashboard
- 100% no-touch campaign selection
- market-data-integrity gates voor shadow/live
- parity harness tussen backtest/paper/shadow/live
- automated candidate demotion/retirement governance

Deze onderdelen maken de machine **slimmer** zonder alpha-complexiteit toe te voegen.

---

# 7. Nieuwe leidende bouwvolgorde

De roadmap wordt daarom:

1. **v3.15.1 — Public Surface Integrity**
2. **v3.15.2 — Autonomous Campaign Operations Layer**
3. **v3.16 — Shadow Deployment & Operational Risk Layer**
4. **v3.17 — Controlled Live Enablement**

Belangrijk:
- v3.15.1 en v3.15.2 zijn geen “extra features”
- ze zijn noodzakelijke operating-system lagen
- zonder deze lagen is meer compute inefficiënt
- zonder deze lagen is shadow/live te vroeg

---

# 8. v3.15.1 — Public Surface Integrity

## 8.1 Doel

De engine operationeel helder en eerlijk maken voor de gebruiker/operator.

## 8.2 Scope

### A. Stale public artifact / banner
Zichtbaar maken wanneer “latest public outputs” stale zijn doordat een recente run degenerate/no-survivor was en dus de public contracts niet overschreef.

### B. Pairs decision surface
`pairs_equities_daily_baseline` expliciet modelleren als:

- disabled
- planned
- product-/roadmapbeslissing
- niet “kapot”
- met rationale, expected behavior, falsification en enablement criteria

## 8.3 Waarom dit eerst moet

Meer automation en meer compute zonder duidelijke latest-surface en zonder heldere preset-beslissing veroorzaakt:

- verkeerde interpretatie
- verspilde operator-aandacht
- onduidelijke campaign-catalog decisions

## 8.4 Definition of Done

- stale public state zichtbaar in API + UI
- latest attempted run ≠ latest public write is expliciet zichtbaar
- unknown/absent freshness state bestaat
- pairs preset is zichtbaar als bewuste disabled/planned beslissing
- frozen contracts onaangetast

---

# 9. v3.15.2 — Autonomous Campaign Operations Layer

## 9.1 Waarom deze fase nieuw en verplicht is

Deze fase is de ontbrekende schakel tussen:

- een werkende research machine
- en een research platform dat zonder handmatig campagnebeheer betekenisvolle throughput kan draaien

Dit is de fase die de machine **slimmer** maakt zonder nieuwe alpha toe te voegen.

## 9.2 Hoofddoel

> 100% autonome campaign-selectie, queueing en standaard follow-up.

De operator mag alleen observeren en policy/governance begrijpen.

## 9.3 Scope

### A. Campaign Template Catalog
First-class campaign types, bijvoorbeeld:

- `daily_primary`
- `daily_control`
- `survivor_confirmation`
- `paper_followup`
- `weekly_retest`
- `shadow_followup`

Templates bepalen:
- eligible presets
- cooldown policy
- priority
- expected outcome type
- repeat rules
- follow-up semantics

### B. Campaign Registry
Nieuwe artifactlaag voor campaign-objecten:

- `campaign_id`
- `campaign_type`
- `preset`
- `spawn_reason`
- `priority`
- `status`
- `worker_eligibility`
- `cooldown_until`
- `spawned_by_run_id`
- `attempt_count`
- `lineage`

### C. Campaign Queue
Artifact-driven queue met:

- pending
- leased
- running
- completed
- failed
- archived
- canceled

### D. Campaign Policy Engine
De kern van deze fase.

Policy engine beslist op artifact-basis:
- welke campagne nu moet draaien
- welke paden in cooldown gaan
- welke structurally dead zijn
- welke survivors confirmatie verdienen
- wanneer paper follow-up moet starten
- wanneer control-runs nodig zijn
- wanneer geen nuttige volgende run bestaat

### E. Longitudinal Evidence Ledger
Cross-run intelligence per:

- preset
- strategy family
- asset cluster
- candidate family
- regime family
- failure mode

Het ledger bewaart:
- hit-rate
- repeated failure modes
- survivor frequency
- paper divergence history
- demotion/retirement evidence
- structural reject counts

### F. Failure Memory as Active Policy
Niet alleen bewaren, maar gebruiken.

Voorbeelden:
- 3× `insufficient_trades` op rij → control-only
- 5× screening reject op dezelfde family zonder verandering → freeze primary allocation
- 2× paper mismatch → retire candidate family
- repeated no-survivor campaign → increase cooldown

### G. Compute Budget Allocator
Per campaign:
- estimated runtime
- information gain score
- compute class
- worker affinity
- retry value
- cooldown cost

Per periode:
- daily compute budget
- reserved shadow/paper capacity
- max low-value reruns
- economic priority tiers

### H. Worker Lease / Admission Control
Voor multi-worker execution:

- lease acquisition
- stale worker recovery
- mutual exclusion
- max concurrent run policy
- queue backpressure
- retry throttling

### I. Campaign Digest
Dagelijkse artifact/report met:
- wat draaide
- wat faalde
- wat follow-up verdient
- welke campaigns bevroren zijn
- welke compute is verbruikt
- wat de top decisions van de policy engine waren

### J. Economics Dashboard
Niet alleen research metrics, maar ook:
- campaigns per dag/week
- meaningful campaigns
- compute spent
- cost per meaningful campaign
- cost per candidate
- cost per paper-worthy candidate
- worker utilization
- queue efficiency

## 9.4 Wat deze fase expliciet niet is

Niet bouwen:
- ML campaign selector
- RL allocator
- autonomous alpha inventor
- hidden heuristic black box
- frontend business logic

Dit blijft:
- expliciet
- deterministic
- artifact-driven
- reviewable

## 9.5 Definition of Done

- 100% campaign-selectie autonoom
- queue en follow-up autonoom
- operator kiest geen volgende run meer
- repeated structural losers worden automatisch gedeprioritiseerd
- survivors worden automatisch geëscaleerd naar confirmatie/paper
- economics metrics zijn zichtbaar
- compute allocator werkt
- failure memory is active policy
- campaign digest bestaat
- worker leases/admission control bestaan

---

# 10. Mei budget sprint (Discovery Throughput Sprint)

## 10.1 Budget
**Mei: €200 extra**

## 10.2 Voorwaarde
Alleen zinvol als:
- v3.15.1 staat
- v3.15.2 kern staat of bijna staat
- campaign queue werkt
- no-touch selectie werkt

## 10.3 Operating model

### Control plane
Bestaande VPS blijft:
- dashboard
- scheduler
- artifact home
- campaign registry / queue
- central digest

### Worker model
Extra compute gebruiken voor:
- 1–2 extra workers
- serieel per worker
- queue gestuurd
- geen ad hoc handmatige starts

## 10.4 Doel voor mei
- **25–50 meaningful campaigns**
- geen random extra runs
- nadruk op:
  - survivor detection
  - family falsification
  - candidate breadth
  - first paper-worthy evidence

## 10.5 Stop/go eind mei
Aan het einde van mei moet minimaal één van deze waar zijn:

1. ten minste één **echte candidate**
2. ten minste één **near-candidate** met duidelijke follow-upreden
3. duidelijke nieuwe informatie over welke family/preset-paths structureel dood zijn

Als niets van dit alles gebeurt:
- geen brute-force opschaling in juni
- eerst hypothese- en catalog review

---

# 11. v3.16 — Shadow Deployment & Operational Risk Layer

## 11.1 Doel

Van paper-validatie naar live-like, maar nog niet order-sending gedrag.

## 11.2 Waarom deze fase pas nu komt

Shadow zonder autonome campaign- en evidence-discipline is te vroeg.  
Je wilt eerst weten dat:
- discovery rationeel draait
- survivors niet ad hoc gekozen zijn
- candidate governance traceable is

## 11.3 Scope

### A. Shadow Execution Mode
- actuele marktdata
- live-like signal generation
- intent generation
- geen echte orders
- dezelfde observability als later live

### B. Operational Risk Layer
- global stop
- candidate stop
- asset stop
- drawdown stop
- anomaly stop
- stale data stop
- feed integrity stop

### C. Monitoring & Alerting
- feed health
- signal heartbeat
- shadow health
- divergence alerts
- latency/freshness alarms
- risk alerts

### D. Post-Intent / Post-Trade Attribution
- expected vs observed
- execution degradation
- slippage drift
- regime mismatch
- cost drift
- candidate degradation

### E. Market Data Integrity Gates
Nieuw expliciet first-class.

Verplicht:
- stale feed detection
- missing bar detection
- timestamp monotonicity
- outlier detection
- session awareness
- event/earnings blackout awareness waar relevant
- broker/feed parity checks zodra relevant

### F. Shadow–Paper–Backtest Parity Harness
Per candidate moet meetbaar zijn:
- signal parity
- order intent parity
- fill-parity proxies
- PnL attribution gap
- timing drift
- slippage decomposition

### G. Candidate Governance Automation
Nieuwe automatische regels:
- paper expiry
- shadow expiry
- shadow demotion
- anomaly-based freeze
- requalification logic

### H. New Lifecycle State
`live_shadow_ready` wordt first-class operational state.

## 11.4 Definition of Done

- minimaal 1 candidate kan shadow-ready worden verklaard
- shadow draait stabiel
- market-data-integrity gates werken
- alerts en kill switches werken
- parity harness werkt
- attribution artifacts zijn bruikbaar
- candidate governance automation bestaat

---

# 12. Juni budget sprint (Shadow / Confirmation Sprint)

## 12.1 Budget
**Juni: €300 extra**

## 12.2 Voorwaarde
Alleen doen als eind mei minimaal één van deze waar is:

- echte candidate
- near-candidate met duidelijke survivor path
- paper-worthy candidate
- overtuigend shadow-ready pad

## 12.3 Doel voor juni
Niet meer “pure discovery first”, maar:
- confirmation
- paper follow-up
- shadow evidence
- live gating readiness

## 12.4 Compute-allocatie in juni
Alleen zinvol als:
- queue discipline werkt
- economics dashboard werkt
- workers zinnig benut worden

Doel:
- 2–4 workers totaal
- reserved capacity voor:
  - confirmation campaigns
  - paper follow-up
  - shadow follow-up
  - beperkte discovery

## 12.5 Juni stop/go gate
Aan het einde van juni moet minimaal één van deze waar zijn:

1. **1 paper-worthy candidate**
2. **1 live_shadow_ready candidate**
3. harde conclusie dat de huidige preset/hypothesis space commercieel te zwak is

## 12.6 Juni kill gate
Als na mei + juni samen:
- 50–100 meaningful campaigns
- 0 paper-worthy candidates
- terugkerende failure modes
- geen nieuwe informatie

dan:
- project herijken of afkappen
- niet blind meer compute inzetten

---

# 13. v3.17 — Controlled Live Enablement

## 13.1 Voorwaarde

Alleen starten als v3.16 minimaal één overtuigende `live_shadow_ready` candidate oplevert.

## 13.2 Doel

Klein, gecontroleerd, rollbackable live.

## 13.3 Scope

### A. Broker Adapter
- submit/cancel/read order state
- positions
- fills
- balances
- idempotency
- retry discipline
- error taxonomy

### B. Position Reconciliation
- engine state vs broker state
- mismatch detectie
- safe-stop bij mismatch
- reconciliation artifacts

### C. Live Risk Envelope
- max capital per candidate
- max total capital
- max exposure per asset
- max daily loss
- max drawdown
- session gating
- concentration caps

### D. Candidate Whitelist
Alleen expliciet toegelaten candidates mogen live.

Nieuwe artifact/control surface:
- live eligibility registry
- whitelist state
- reason codes

### E. Hard Kill Switches
- global stop
- asset stop
- candidate stop
- data stop
- broker disconnect stop
- reconciliation mismatch stop

### F. Retirement / Demotion Logic
- live → shadow
- shadow → retired
- live → retired
- candidate degradation tracking
- paper revalidation requirements

### G. Tiny-Capital Burn-In
Verplicht:
- klein kapitaal
- klein aantal candidates
- beperkte asset scope
- expliciete rollback path

### H. Economic Stop/Go Metrics
Niet alleen technische live-health, maar ook:
- cost per live day
- realized divergence vs shadow/paper
- burn-in PnL attribution
- threshold voor opschalen of stoppen

## 13.4 Live MVP

- 1 broker
- 1 candidate
- klein kapitaal
- kleine whitelist
- volledige monitoring
- volledige reconciliation
- instant rollback

## 13.5 Definition of Done

- 1 live-enabled candidate
- met klein kapitaal
- met bewezen rollback
- met bewezen reconciliation
- met werkende kill switches
- met live-vs-shadow-vs-paper attribution
- met live demotion/retirement path

---

# 14. Pairs track als formeel branchpoint

## 14.1 Waarom dit expliciet moet

`pairs_equities_daily_baseline` is nu:
- disabled
- planned
- inhoudelijk anders dan directional trend of crypto MR

De orchestrator-spec bevat pairs/stat arb expliciet in de core strategy universe.  
Dus pairs kan niet eeuwig als impliciete placeholder blijven bestaan.

## 14.2 Wat de roadmap moet doen

Niet:
- stiekem enable-en

Wel:
- formeel beslismoment opnemen

## 14.3 Branchpoint options
Er moet een expliciete decision gate komen:

1. **Enable in future discovery queue**
2. **Keep disabled until post-v3.17**
3. **Retire as out-of-scope**

## 14.4 Benodigde criteria vóór enablement
Minimaal:
- mathematisch passende spread/hedge-ratio support
- correct pairs lineage
- correct candidate diagnostics voor stat arb
- geen architectuurdrift
- duidelijke expected behavior en falsification

---

# 15. Wat nadrukkelijk níet op de roadmap moet worden toegevoegd vóór v3.17 stabiel is

Niet doen vóór bovenstaande fasen stabiel zijn:

- ML campaign selector
- RL allocation
- deep learning alpha
- strategy explosion
- complex macro forecasting alpha
- optimizer-heavy capital allocation
- broad live automation
- autonome opschaling van live kapitaal
- fancy ranking buiten deterministische scoring

Leidend blijft:

- architectuur boven snelheid
- falsificatie boven storytelling
- OOS boven IS
- DSR boven raw Sharpe
- robuustheid boven topresultaat
- paper vóór shadow/live
- expliciete policy boven hidden intelligence

---

# 16. Nieuwe exit criteria op platformniveau

## 16.1 Campaign automation
Oude formulering:
- minimaal 80% van campaign-selectie gebeurt zonder handmatig kiezen

Nieuwe harde formulering:
> **100% van campaign-selectie, campaign-enqueueing en standaard follow-up gebeurt zonder handmatige keuze.**

De operator mag alleen:
- policy-tiers bekijken
- economics bekijken
- expliciete governancebesluiten nemen
- noodstop/stop-go beslissingen nemen

## 16.2 Evidence
Niet één losse run telt, maar:
- longitudinal evidence
- repeated failure modes
- survivor stability over tijd
- compute efficiency

## 16.3 Economics
De machine moet kunnen rapporteren:
- cost per meaningful campaign
- cost per candidate
- cost per paper-worthy candidate
- cost per shadow-ready candidate

---

# 17. Praktische beslisstructuur voor mei en juni

## Eind mei — gate
Doorgaan naar juni alleen als er minimaal één van deze is:
- echte candidate
- near-candidate
- survivor path naar paper/shadow
- nieuwe information gain van voldoende kwaliteit

## Eind juni — gate
Doorgaan naar verdere live-enablement alleen als:
- paper-worthy candidate bestaat
- of live_shadow_ready candidate bestaat

Anders:
- herijken
- of afkappen

---

# 18. Progress tracker v3

Gebruik dit blok om voortgang vast te leggen.

## Gebouwd
- [x] v3.11 Research Quality Engine
- [x] v3.12 Candidate Promotion Framework
- [x] v3.13 Regime Intelligence & Gating
- [x] v3.14 Portfolio / Sleeve Research
- [x] v3.15 Paper Validation Engine

## Nog te bouwen
- [ ] v3.15.1 Public Surface Integrity
- [ ] v3.15.2 Autonomous Campaign Operations Layer
- [ ] v3.16 Shadow Deployment & Operational Risk Layer
- [ ] v3.17 Controlled Live Enablement

## Autonomous Campaign Ops
- [ ] campaign template catalog
- [ ] campaign registry
- [ ] campaign queue
- [ ] campaign policy engine
- [ ] longitudinal evidence ledger
- [ ] compute budget allocator
- [ ] worker lease/admission control
- [ ] campaign digest
- [ ] economics dashboard
- [ ] 100% no-touch campaign selection

## Shadow / Risk
- [ ] shadow mode
- [ ] market data integrity gates
- [ ] parity harness
- [ ] alerting
- [ ] risk stops
- [ ] candidate governance automation

## Live
- [ ] broker adapter
- [ ] reconciliation
- [ ] live whitelist
- [ ] live risk envelope
- [ ] kill switches
- [ ] retirement/demotion logic
- [ ] tiny-capital burn-in

---

# 19. Eén-zin samenvatting

> **De volgende kwaliteitsstap zit niet in meer strategieën, maar in een volledig autonome campaign-operating layer die compute als schaars kapitaal behandelt, survivors automatisch doorzet, repeated losers automatisch wegfiltert, en pas daarna via shadow en gecontroleerd live een eerste echt deployable candidate mogelijk maakt.**
