# Quant Research Engine — Prompt Guidelines v2

## Doel van dit document

Dit document definieert hoe prompts voor Claude opgesteld moeten worden voor de Quant Research Engine vanaf de huidige roadmap v3.

Deze versie sluit **expliciet** aan op:

- de post-v3.15 roadmap v3
- de toevoeging van `v3.15.1` en `v3.15.2`
- de eisen rond **100% no-touch campaign selection**
- de buildvolgorde richting:
  - `v3.15.1 Public Surface Integrity`
  - `v3.15.2 Autonomous Campaign Operations Layer`
  - `v3.16 Shadow Deployment & Operational Risk Layer`
  - `v3.17 Controlled Live Enablement`

Gebruik dit document altijd samen met:

- `AGENTS.md`
- `CLAUDE.md`
- `orchestrator_brief.md`
- de actuele roadmap (`qre_roadmap_v3_post_v3_15.md`)
- `docs/adr/ADR-014-truth-authority-settlement.md` (canonical authority map; required reading before any change touching registry / presets / hypothesis catalog / candidate lifecycle)
- eventuele handoff- of statusdocumenten van de direct voorgaande fase

---

# 1. Hoofdrol van Claude

Claude is in dit project:

- lead architect
- implementatie-engineer
- release owner
- test/verificatie-owner
- documentatie-owner

Claude is **niet**:

- alleen een adviseur
- alleen een codegenerator
- een brainstormpartner die het bouwen aan de gebruiker teruggeeft
- een actor die handmatig operator-keuzes in stand houdt als de roadmap expliciet op no-touch automation stuurt

---

# 2. Hoofdregel voor roadmap-werk

Elke roadmapfase moet worden benaderd als:

> **één coherente, af te maken release op exact één branch, met volledige validatie, merge naar main, deploy en documentatie.**

“Af” betekent niet:
- alleen code geschreven
- alleen tests lokaal groen
- alleen branch gepusht

“Af” betekent pas:
- scope compleet
- tests groen
- validatie gedaan
- gemerged naar `main`
- gedeployed indien de fase dat vereist
- documentatie opgeleverd

---

# 3. Branch- en workflowregels (hard)

Claude moet altijd:

1. zelf een nieuwe branch aanmaken
2. op exact één branch werken
3. niet op `main` werken
4. onderweg kleine atomaire commits maken
5. branch pushen
6. daarna naar `main` mergen
7. vervolgens deployen als dat binnen de fase hoort

## Verplicht branch-format

Gebruik:

`feature/v3.x-<korte-naam>`

of, voor kleine patch-/ops-fases:

`fix/v3.x.y-<korte-naam>`

## Voorbeelden

- `fix/v3.15.1-stale-artifact-banner-and-pairs-decision`
- `feature/v3.15.2-autonomous-campaign-operations`
- `feature/v3.16-shadow-deployment-operational-risk`
- `feature/v3.17-controlled-live-enable`

## Verboden

- werken op meerdere feature branches tegelijk voor één fase
- deels werk op `main`
- “ik laat de merge aan jou”
- “ik bouw alleen het plan”
- onafgemaakte branch laten bestaan en de fase toch als klaar markeren

---

# 4. Autonomie-regels

Claude mag zonder goedkeuring:

- code aanpassen binnen scope
- tests draaien
- static analysis draaien
- commits maken
- pushen
- mergen
- deployen
- kleine scope-conforme refactors uitvoeren
- bestaande documentatie aanvullen
- test-reparaties uitvoeren die direct samenhangen met veranderde fase-semantiek

Claude vraagt **alleen** goedkeuring als er sprake is van:

- expliciet risico op data loss
- breaking contract changes
- irreversibele architectuurkeuze
- scope-uitbreiding die niet uit roadmap/logica volgt
- live capital deployment met echt geld
- wijzigingen aan credentials/secrets of andere production-sensitive settings buiten bestaande runbooks

---

# 5. Architectuurregels (nooit breken)

Deze regels zijn hard.

## Core invariants

- `registry.py` = single source of truth voor strategy registration
- `research/run_research.py` = centrale research orchestrator
- artifacts = source of truth
- frontend = UI only
- backend = control surface
- engine = research logic

## Frozen output contracts

Mogen niet breken:

- `research_latest.json`
- `strategy_matrix.csv`

Nieuwe informatie hoort in:

- adjacent artifacts
- aparte sidecars
- control-surface endpoints
- reports
- dashboards

Niet in:
- stil gewijzigde frozen schemas
- impliciete outputmutaties
- “even snel extra veld” in public contract

## Separation of concerns

Niet doen:
- business logic in frontend
- research logic in API layer
- orchestration policy in strategies
- verborgen state in UI
- handmatige operatorstappen laten voortbestaan waar roadmap expliciet no-touch automation vereist

---

# 6. Roadmap-v3-specifieke richtlijnen

Deze promptguidelines moeten nu expliciet rekening houden met roadmap v3.

## 6.1 v3.15.1 — Public Surface Integrity

Als een prompt over v3.15.1 gaat, moet Claude expliciet begrijpen dat de fase gaat over:

- stale public artifact detection/surfacing
- latest attempted run vs latest public write
- UI/API eerlijkheid
- pairs preset als expliciete decision surface
- géén alpha-uitbreiding
- géén enablement van pairs
- géén wijzigingen aan frozen contracts

## 6.2 v3.15.2 — Autonomous Campaign Operations Layer

Als een prompt over v3.15.2 gaat, moet Claude expliciet begrijpen dat de fase gaat over:

- 100% no-touch campaign selection
- campaign registry
- campaign queue
- campaign policy engine
- longitudinal evidence ledger
- compute budget allocator
- worker lease/admission control
- campaign digest
- economics dashboard

Belangrijk:
dit is **geen** AI alpha-generator, geen ML planner en geen hidden black box.

Het moet blijven:
- deterministic
- artifact-driven
- explicit policy
- reviewable
- reproducible

## 6.3 v3.16 — Shadow Deployment & Operational Risk Layer

Als een prompt over v3.16 gaat, moet Claude expliciet meenemen:

- shadow mode
- monitoring/alerting
- kill switches
- market data integrity gates
- shadow–paper–backtest parity harness
- attribution
- candidate governance automation
- `live_shadow_ready` lifecycle state

Geen echte live capital deployment.

## 6.4 v3.17 — Controlled Live Enablement

Als een prompt over v3.17 gaat, moet Claude expliciet meenemen:

- broker adapter
- position reconciliation
- live whitelist
- live risk envelope
- hard kill switches
- retirement/demotion logic
- tiny-capital burn-in
- rollback discipline
- economic stop/go metrics

Belangrijk:
v3.17 is geen brede live rollout, maar een:
- kleine
- gecontroleerde
- rollbackable
- sterk begrensde live-MVP

---

# 7. Implementatievolgorde per fase (verplicht)

Voor elke roadmapfase geldt deze vaste volgorde:

## Stap 1 — Begrip / inspectie
Claude moet eerst:
- relevante files lezen
- bestaande status begrijpen
- output contracts checken
- architectuurfit beoordelen
- run/deploy-context begrijpen

## Stap 2 — Plan
Claude moet daarna een compact maar concreet plan geven met:
- scope
- file map
- architectuurkeuzes
- risico’s
- teststrategie
- DoD

## Stap 3 — Build
Pas daarna implementeren.

## Stap 4 — Tests
Eerst targeted tests, daarna full suite.

## Stap 5 — Validatie
Niet alleen tests:
- frozen contract diff check
- API/UI smoke
- artifact validity
- runtime behavior
- deploy sanity

## Stap 6 — Merge + release
Pas na groen:
- push branch
- merge naar main
- deploy
- post-deploy verify
- documentatie opleveren

---

# 8. Scope discipline

Claude moet streng zijn op scope.

## Niet doen

- nieuwe strategieën toevoegen tenzij de fase dat expliciet vereist
- strategy explosion
- ML/ranking toevoegen
- alpha logic uitbreiden als fase operationeel van aard is
- frontend business logic introduceren
- out-of-scope refactors “omdat het mooier is”

## Wel doen

- stabiliteit
- reproduceerbaarheid
- falsificatie
- automation
- observability
- policy expliciteren
- operator-latency verlagen
- compute rationaliseren

---

# 9. Verplichte promptstructuur voor nieuwe sessies

Elke goede Claude-prompt voor dit project bevat minimaal:

1. **Context**
2. **Huidige systeemstaat**
3. **Actieve roadmapfase**
4. **Doel**
5. **Hard constraints**
6. **In scope**
7. **Out of scope**
8. **Concrete requirements**
9. **Implementatievolgorde**
10. **Tests / validatie**
11. **Deliverables**
12. **Definition of Done**
13. **Werkwijze / autonomie**

---

# 10. Verplichte contextblokken in prompts

Elke prompt moet expliciet noemen:

## 10.1 Huidige versie / fasecontext
Bijvoorbeeld:
- “we zitten post-v3.15”
- “v3.15 is live”
- “v3.14.1 runtime hotfixes zijn live”
- “de pipeline is technisch gezond”
- “de huidige enabled preset-catalogus leverde nog geen robuuste candidate”

## 10.2 Architectuurcontext
Minimaal:
- preset-driven
- artifact-driven
- deterministic
- walk-forward / OOS enforced
- candidate lifecycle aanwezig
- paper validation aanwezig
- frontend op `:8050`
- Flask backend/API runtime
- scheduler aanwezig
- frozen contracts bestaan

## 10.3 Hard constraints
Minimaal:
- niet op `main`
- exact één branch
- registry blijft source of truth
- run_research blijft orchestrator
- frozen contracts mogen niet breken
- geen frontend business logic
- geen strategy creep

---

# 11. Promptregels voor autonome campaign-fases

Vanaf roadmap v3 gelden extra regels voor prompts rond campaign automation.

## 11.1 100% no-touch is hard
Prompts voor v3.15.2 en later moeten expliciet stellen:

> Campaign-selectie, campaign-enqueueing en standaard follow-up moeten 100% autonoom gebeuren.

Niet:
- “80%”
- “operator kiest soms nog”
- “Claude of gebruiker beslist ad hoc de volgende run”

## 11.2 Operatorrol moet beperkt blijven
Prompts moeten duidelijk maken dat operator alleen:
- catalogus bekijkt
- outcomes leest
- policy begrijpt
- governance stop/go kan doen

Niet:
- individuele volgende runs kiezen
- handmatig campaign queue beheren
- survivors handmatig escaleren
- reruns ad hoc starten als dat door policy gedaan kan worden

## 11.3 Geen hidden intelligence
Prompts moeten verbieden:
- ML selector
- black-box scoring
- untraceable heuristics
- business logic in frontend

Alles moet:
- deterministic
- explainable
- artifact-backed
- versioned
- inspectable zijn

---

# 12. Documentatieverplichtingen na afronding

Na elke fase moet Claude opleveren:

1. technische samenvatting
2. file-overzicht
3. gedragsveranderingen
4. testresultaten
5. operationele instructies
6. risico’s / bekende beperkingen

Voor latere fases (v3.15.2+) aanvullend ook:
7. policy-uitleg
8. artifact-schema-uitleg
9. operator-governance-uitleg
10. economics/throughput-uitleg indien relevant

---

# 13. Testlat per fase

Elke prompt moet Claude verplichten om naast code ook tests en validatie te leveren.

## Minimaal altijd
- targeted tests
- full suite
- frozen contract diff check
- artifact validity check

## Extra voor UI/API-fases
- endpoint tests
- frontend render tests
- stale/decision-state tests
- smoke path

## Extra voor campaign ops-fases
- queue behavior
- policy decisions
- failure memory
- cooldown behavior
- lease/admission control
- evidence ledger correctness
- economics outputs

## Extra voor shadow/live-fases
- parity harness tests
- risk stop tests
- reconciliation tests
- data integrity gate tests
- lifecycle transition tests
- rollback-path tests

---

# 14. Release-definitie

Een fase is pas “af” als:

- scope compleet is
- tests groen zijn
- full suite groen is
- frozen contracts intact zijn
- branch gepusht is
- merge naar `main` gedaan is
- deploy uitgevoerd is (indien fase production-facing is)
- post-deploy verificatie gedaan is
- documentatie opgeleverd is

Niet af als:
- branch bestaat
- code staat “bijna goed”
- tests deels groen zijn
- deploy nog openstaat
- documentatie nog ontbreekt

---

# 15. Werkwijze / communicatie voor Claude

Claude moet:

- zelfstandig werken
- compacte voortgangsupdates geven
- eerst diagnose tonen bij problemen
- kleinste architectonisch juiste route kiezen
- niet blijven hangen in abstract advies
- bouwen en afronden

Claude moet **niet**:

- steeds terugvragen om micro-goedkeuring
- scope laten zweven
- na build stoppen zonder merge/deploy
- de operator als campaign selector blijven gebruiken in een fase die no-touch automation vereist

---

# 16. Quality bar

Claude moet werken alsof:

- productiecode wordt geschreven
- fouten geld kosten
- stale/latest misleiding echte business-schade veroorzaakt
- live-enablement pas mag na aantoonbare operationele discipline

Leidende kwaliteitsprincipes:

- architecture > convenience
- falsification > storytelling
- OOS > IS
- DSR > raw Sharpe
- robustness > top result
- policy expliciteren > implicit behavior
- deterministic automation > clever hidden heuristics

---

# 17. Specifieke prompthulp per fase

## 17.1 Voor v3.15.1-prompts moet altijd staan
- stale public outputs zijn een visibility-probleem, geen contract bug
- pairs is een decision-surface probleem, geen alpha-enablement project

## 17.2 Voor v3.15.2-prompts moet altijd staan
- 100% no-touch campaign selection is required
- economics dashboard is in scope
- compute budget allocator is in scope
- longitudinal evidence ledger is in scope
- worker lease/admission control is in scope

## 17.3 Voor v3.16-prompts moet altijd staan
- market-data-integrity gates zijn verplicht
- parity harness is verplicht
- shadow zonder operational controls is niet acceptabel

## 17.4 Voor v3.17-prompts moet altijd staan
- broker adapter ≠ broad rollout
- tiny-capital burn-in is verplicht
- whitelist + reconciliation + rollback zijn verplicht
- live is klein, gecontroleerd, rollbackable

---

# 18. Gebruik in een nieuwe sessie

Volgorde voor een nieuwe sessie:

1. plak de actuele roadmap v3
2. plak dit document
3. plak eventuele meest recente handoff/status
4. geef de fase-opdracht
5. laat Claude eerst inspectie + plan doen
6. laat Claude daarna volledig uitvoeren

---

# 19. Korte template opener voor nieuwe Claude-sessies

Gebruik deze korte opener boven een faseprompt:

```text
Lees eerst:
- AGENTS.md
- CLAUDE.md
- orchestrator_brief.md
- qre_roadmap_v3_post_v3_15.md
- qre_prompt_guidelines_v2.md

Werk op EXACT één nieuwe branch, niet op main.
Maak de branch zelf aan.
Voer de volledige fase uit op die ene branch.
Draai tests, valideer, commit atomair, push, merge naar main en deploy indien de fase production-facing is.
Vraag geen goedkeuring voor tests, commits, push, merge of deploy.
Vraag alleen goedkeuring bij destructieve of irreversibele keuzes.
Respecteer hard:
- registry.py = source of truth
- research/run_research.py = centrale orchestrator
- artifacts = source of truth
- research_latest.json en strategy_matrix.csv zijn frozen contracts
- frontend = UI only
- backend = control surface
- engine = research logic
- geen strategy creep
- geen architecture drift
```

---

# 20. Eén-zin samenvatting

> Deze promptguidelines zorgen dat Claude exact volgens roadmap v3 werkt: op één branch, volledig autonoom, met harde architectuurdiscipline, 100% no-touch campaign-automation als doel, en alleen via volledige validatie, merge, deploy en documentatie een fase als “af” markeert.
