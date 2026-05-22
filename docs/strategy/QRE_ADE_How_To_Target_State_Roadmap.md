---
title: "QRE + ADE - Van huidige staat naar target state"
subtitle: "De how: implementatieroute, lessons learned, data-throughput, governance en autonome research maturity"
author: "Engineering sparringsdocument voor Joery van Rooij"
date: "2026-05-22"
lang: nl-NL
---


# Inhoudsopgave

1. Executive summary
2. Begrippenkader
3. Huidige staat
4. Target state
5. Lessons learned
6. Anti-valkuil systeem
7. De centrale strategie: van minimal loop naar trusted loop
8. Hoofdroute: van nu naar target state
9. Data-throughput ontwerp
10. Research memory ontwerp
11. Governance en authority model
12. Concrete implementatiepromptbibliotheek
13. KPI framework
14. Risicoregister
15. Beslisregels voor technologie
16. Implementatieritme
17. De eerste 10 concrete stappen
18. Wat voorlopig bewust niet doen
19. Target operating model
20. Eindbeeld per maturity laag
21. Slotadvies
Appendices

\newpage

# Documentdoel

Dit document beantwoordt de grote vraag: **hoe komen we vanaf de huidige staat naar de target state, met alle lessons learned verwerkt?**

Het is bewust geen korte roadmap. Het is een uitvoerbaar strategisch werkdocument voor de volgende fase van het project. Het combineert:

- wat we achteraf anders hadden moeten aanpakken;
- hoe we voortaan beter leren van het verleden;
- waar het systeem nu staat;
- waar het uiteindelijk naartoe moet;
- welke bottlenecks nu het meest bepalend zijn;
- welke volgorde de hoogste kans van slagen geeft;
- hoe ADE en QRE elkaar moeten versterken zonder elkaar te vervuilen;
- hoe data door de hele keten moet gaan stromen;
- hoe operator-control behouden blijft terwijl handwerk afneemt.

De kernboodschap:

```text
Niet meer lagen toevoegen omdat ze interessant zijn.
Eerst de bestaande minimal loop bewijzen, kalibreren en voeden met betrouwbare data.
Daarna pas meer autonomie.
```

---

# 1. Executive summary

## 1.1 De target state in een zin

De target state is:

```text
Een deterministic, auditbare, behavior-first quant research engine
met een veilige autonome ontwikkellaag eromheen,
die systematisch marktgedrag falsifieert, research memory opbouwt,
zelf vervolgonderzoek prioriteert en pas helemaal aan het einde via
shadow -> paper -> controlled live naar deployment mag groeien.
```

Of korter:

```text
QRE moet leren wat onderzocht moet worden.
ADE moet veilig leren hoe QRE verder gebouwd moet worden.
De operator wil minder handwerk, maar niet minder grip.
```

## 1.2 Wat is nu veranderd door de laatste stand van zaken

De laatste stand laat zien dat het project verder is dan alleen governance en roadmapplanning. In de laatste week zijn zowel ADE als QRE fors doorgebouwd.

Belangrijke observatie:

```text
ADE is van documentatie/governance gegroeid naar een bounded development conveyor.
QRE is van roadmap/intentie gegroeid naar minimale slices van de Roadmap v6 research-intelligence loop.
```

Er zijn minimale QRE-slices voor:

- v3.15.16 Intelligent Routing;
- v3.15.17 Sampling Intelligence;
- v3.15.18 Research Observability;
- v3.15.19 Hypothesis Discovery;
- v3.15.20 Failure Action Mapping;
- v3.16.x Adaptive Research Learning;
- controlled research evaluation;
- no-candidate diagnostics;
- research decision state;
- research action planning;
- policy filter diagnostics;
- screening failure attribution;
- synthesis eligibility gate.

Daarom is de vraag niet meer:

```text
Welke lagen ontbreken nog?
```

Maar:

```text
Zijn de lagen al inhoudelijk krachtig genoeg om betere researchbeslissingen te nemen?
```

## 1.3 De grootste huidige bottleneck

De grootste bottleneck is niet een ontbrekende strategie. De grootste bottleneck is:

```text
De research loop bestaat nu minimaal, maar moet bewijzen dat hij echte failures kan verklaren,
echte data betrouwbaar kan verwerken en betere vervolgstappen kan kiezen dan handmatige operator-intuitie.
```

Daaronder liggen drie sub-bottlenecks:

1. **Failure attribution**: te veel failures blijven onbekend of te grof geclassificeerd.
2. **Data throughput en data authority**: data moet quality-gated, reproduceerbaar en herbruikbaar door de hele keten.
3. **Learning discipline**: leren mag niet black-box worden; het moet deterministic, evidence-backed en auditbaar blijven.

## 1.4 De aanbevolen route

De aanbevolen route is:

```text
0. Stabiliseer huidige minimal loop
1. Reduceer unknown failures
2. Bouw data foundation als productlaag
3. Maak research memory first-class
4. Kalibreer routing/sampling op echte evidence
5. Maak observability operator-grade
6. Verdiep hypothesis discovery zonder strategy invention
7. Sluit failure -> action -> reroute loop
8. Bouw adaptive learning met deterministic metrics
9. Pas daarna shadow
10. Pas daarna paper
11. Pas daarna controlled live
```

De belangrijkste ontwerpregel:

```text
Autonomie mag pas toenemen nadat explainability, authority boundaries, data quality en failure memory toenemen.
```

---

# 2. Begrippenkader

## 2.1 QRE

QRE staat voor Quant Research Engine. De QRE is het product dat marktgedrag onderzoekt. De QRE moet uiteindelijk:

- marktdata en contextbronnen verwerken;
- gedragshypotheses formuleren;
- hypotheses prioriteren;
- campaigns plannen en uitvoeren;
- resultaten falsificeren;
- failures onthouden;
- vervolgstappen bepalen;
- candidates door governance trekken;
- pas later shadow/paper/live deployment ondersteunen.

De QRE is geen tradingbot in de klassieke zin. De QRE is een research operating system.

## 2.2 ADE

ADE staat voor Autonomous Development Engine of Autonomous Development Environment. ADE is niet de tradinglaag. ADE is de ontwikkel- en governance-laag die helpt om QRE veilig te bouwen.

ADE mag:

- roadmapwerk decomposen;
- authority classificeren;
- veilige units selecteren;
- branches/PRs voorbereiden binnen governance;
- tests draaien;
- CI/merge workflows ondersteunen;
- operator-visible statusrapporten maken.

ADE mag niet:

- live trades plaatsen;
- trading authority krijgen;
- broker/risk/live paths muteren zonder expliciete fase en operator-go;
- zichzelf boven governance plaatsen;
- branch protection of hooks omzeilen.

## 2.3 Trading/research execution

Dit is een aparte domeinlaag. Het gaat over:

- strategies runnen;
- campaigns uitvoeren;
- shadow decisions loggen;
- paper orders simuleren;
- live orders plaatsen;
- risk envelopes;
- broker adapters;
- capital allocation.

Deze laag mag pas groeien volgens expliciete Roadmap v6-fases:

```text
v4.x Shadow
v5.x Paper
v6.x Controlled Live
```

ADE-authority is nooit automatisch trading-authority.

## 2.4 De operator

De operatorrol verschuift van handmatige campaign selector naar governance en interpretatie:

Oud:

```text
Operator bedenkt strategie -> vraagt Codex -> draait backtest -> interpreteert -> kiest volgende run.
```

Nieuw:

```text
QRE stelt researchactie voor -> operator ziet waarom -> governance bewaakt grenzen -> QRE leert van evidence.
```

De operator blijft eigenaar van:

- missie;
- risk appetite;
- live enablement;
- roadmapprioriteit;
- irreversible architecture decisions;
- acceptatie van high-risk governance changes.

---

# 3. Huidige staat

## 3.1 Samenvatting van de laatste stand

Op basis van de laatste weekly build summary zijn in korte tijd veel mainline commits geland. De commits laten twee hoofdlijnen zien:

1. ADE/governance is verhard en geautomatiseerd.
2. QRE Roadmap v6 core is minimaal geactiveerd.

De laatste QRE-commits van 2026-05-22 zijn bijzonder belangrijk. Ze bouwen een no-candidate diagnoseketen:

- `research/controlled_eval.py`
- `research/research_state.py`
- `research/research_action_plan.py`
- `research/policy_filter_diagnostics.py`
- `research/screening_failure_attribution.py`
- `research/synthesis_gate.py`

Dit betekent dat QRE niet alleen probeert candidates te vinden, maar ook begint te verklaren waarom candidates ontbreken.

## 3.2 ADE-status

ADE heeft nu bouwstenen voor:

- roadmap task catalog;
- roadmap implementation unit decomposer;
- roadmap unit authority classifier;
- read-only operator visibility;
- deterministic next-buildable-unit selector;
- dynamic unit status ledger;
- bounded autonomous PR runner;
- bounded auto-merge voor veilige runner-originated PRs;
- continuous autonomous conveyor;
- unit-templated external implementation commands;
- recorded-fixture simulator;
- dry-run merge execution paths;
- ADE Development-Lane Doctrine.

Interpretatie:

```text
ADE is niet langer alleen een set afspraken.
ADE is een beginnende ontwikkelstraat met policy, queue, authority en feedback.
```

Belangrijk risico:

```text
Sommige Step 5 / auto-merge / conveyor elementen moeten scherp op authority worden bewaakt.
```

De waarde is groot, maar de valkuil ook: zodra ADE te veel uitvoeringsmacht krijgt zonder auditability, wordt snelheid belangrijker dan safety.

## 3.3 QRE-status

QRE heeft minimale slices voor:

- Intelligent Routing;
- Sampling Intelligence;
- Research Observability;
- Hypothesis Discovery;
- Failure Action Mapping;
- Adaptive Research Learning;
- Controlled Evaluation;
- No-Candidate Diagnostics;
- Policy Filter Diagnostics;
- Screening Failure Attribution;
- Research Action Planning;
- Synthesis Eligibility.

Interpretatie:

```text
De research-intelligence skeleton bestaat.
Nu moet hij inhoudelijk volwassen worden.
```

De vraag is niet: "kunnen we nog een module toevoegen?"

De vraag is:

```text
Kan de keten op echte artifacts bewijzen waarom iets faalt en wat rationeel de volgende actie is?
```

## 3.4 Waar het systeem nu waarschijnlijk nog zwak is

De huidige minimal loop is waarschijnlijk nog zwak op:

1. **Attribution depth**: unknown failures zijn nog te groot.
2. **Data readiness**: data quality en coverage zijn nog geen harde gates door de hele keten.
3. **Lineage completeness**: niet elke researchactie heeft volledige bron -> hypothese -> campaign -> evidence -> policy lineage.
4. **Actionability**: niet elke diagnose leidt tot een duidelijke next action.
5. **Research memory**: eerdere failures zijn nog niet maximaal herbruikbaar als context voor routing/sampling.
6. **Operator trust**: de operator moet nog kunnen zien of QRE echt betere beslissingen neemt.
7. **Minimal versus mature confusion**: modules bestaan, maar bestaan is niet hetzelfde als capability.

---

# 4. Target state

## 4.1 De eindarchitectuur

De target architecture is:

```text
Source Candidate Registry
-> Source Identity & Symbology Layer
-> Source Manifest & Quality Gate Layer
-> Local Data Cache & Throughput Layer
-> External Intelligence Intake
-> Research Knowledge & Retrieval Layer
-> State & Sequential Diagnostics Layer
-> Mechanistic Behavior Diagnostics Layer
-> Market Behavior Layer
-> Hypothesis Discovery Layer
-> Strategy Mapping
-> Preset Layer
-> Campaign Layer
-> Funnel Layer
-> Evidence Layer
-> Policy Layer
-> Shadow
-> Paper
-> Controlled Live
```

Maar belangrijk: dit is een volwassenheidsrichting, geen toestemming om alles nu te bouwen.

## 4.2 Target state voor QRE

QRE moet uiteindelijk kunnen:

1. **Data begrijpen**
   - bronkwaliteit;
   - instrumentidentiteit;
   - coverage;
   - freshness;
   - source agreement;
   - allowed use.

2. **Marktgedrag structureren**
   - behavior families;
   - regime states;
   - volatility transitions;
   - entropy states;
   - tail regimes;
   - post-shock behavior;
   - network/context states.

3. **Hypotheses genereren**
   - behavior-first;
   - deterministic;
   - explainable;
   - expected research value, geen alpha confidence;
   - campaign seeds, geen executable strategy invention.

4. **Slim testen**
   - routing op information gain;
   - sampling op coverage en failure likelihood;
   - null-model challenges;
   - OOS discipline;
   - costs en robustness.

5. **Failures leren gebruiken**
   - failure taxonomy;
   - failure-to-action mapping;
   - cooldown;
   - suppression;
   - escalation;
   - regime segmentation;
   - source usefulness updates.

6. **Evidence interpreteren**
   - survivor quality;
   - near-pass;
   - policy filters;
   - synthesis eligibility;
   - candidate lifecycle;
   - paper/shadow readiness.

7. **Operator uitlegbaarheid leveren**
   - waarom explored;
   - waarom failed;
   - waarom next action;
   - welke data/source/diagnostics betrokken waren;
   - welke policy gate blokkeerde.

## 4.3 Target state voor ADE

ADE moet uiteindelijk:

- veilige roadmap units kunnen selecteren;
- authority correct toepassen;
- PRs binnen scope uitvoeren;
- tests en CI betrouwbaar volgen;
- final status reports produceren;
- operator-inbox actionable houden;
- false positives verminderen;
- no-touch/live boundaries bewaken;
- QRE versnellen zonder QRE te sturen als trading actor.

ADE target state:

```text
Development automation with governed autonomy.
Geen trading autonomy.
Geen hidden authority.
Geen uncontrolled merge/deploy behavior.
```

## 4.4 Target state voor de operator

De operator moet kunnen sturen op:

- roadmapprioriteit;
- risk boundaries;
- live/paper/shadow gates;
- governance exceptions;
- interpretation van research outcomes;
- acceptance of irreversible architecture choices.

Maar de operator moet niet meer hoeven:

- handmatig elke campaign kiezen;
- zelf elke failure interpreteren;
- telkens dezelfde context aan Codex uitleggen;
- incomplete statusrapporten reconstrueren;
- data quality met de hand checken;
- roadmaplagen mentaal bijhouden.

---

# 5. Lessons learned

## 5.1 Wat achteraf anders had gemoeten

### Les 1 - Eerst domeinscheiding, dan snelheid

Het project had vanaf dag nul harder moeten scheiden tussen:

```text
ADE development authority
QRE research intelligence
Trading execution authority
```

Zonder deze scheiding ontstaat verwarring rond woorden als "execution", "autonomy" en "agent".

### Les 2 - Eerst data als productlaag, dan strategy work

Data had niet behandeld moeten worden als input voor backtests, maar als eigen productlaag met:

- identity;
- manifests;
- quality gates;
- cache;
- lineage;
- coverage;
- source usefulness.

### Les 3 - Hypothesis first, strategy second

De eerste researchvraag moet niet zijn:

```text
Welke indicatorcombinatie werkt?
```

Maar:

```text
Welk persistent market behavior bestaat mogelijk, en hoe falsificeren we dat?
```

### Les 4 - Failure memory vanaf dag een

Elke negatieve uitkomst had vanaf het begin een first-class record moeten krijgen.

Failure is niet afval. Failure is research capital.

### Les 5 - Dashboard read-only houden totdat governance volwassen is

Een dashboard is verleidelijk, maar mutation controls komen vaak te vroeg.

Eerst:

```text
read-only observability
```

Daarna pas:

```text
governed operator actions
```

### Les 6 - Minimal implementation is niet hetzelfde als capability

Een module die bestaat, is niet automatisch waardevol.

Capability bestaat pas als:

- de output wordt gebruikt;
- de output decision quality verbetert;
- regressietests de behavior bewaken;
- de operator het resultaat kan interpreteren;
- een oude failure mode aantoonbaar minder waarschijnlijk wordt.

### Les 7 - Geen self-learning zonder deterministic feedback

"Self-learning" klinkt aantrekkelijk, maar zonder guardrails wordt het black-box behavior.

QRE-learning moet bestaan uit:

- deterministic metrics;
- failure-to-action mappings;
- evidence-backed routing updates;
- source usefulness;
- behavior-family fitness;
- observable policy changes.

Niet uit:

- verborgen ML selectors;
- LLM strategy invention;
- stochastic mutation;
- live risk adaptation.

---

# 6. Anti-valkuil systeem

## 6.1 Het Operator Learning System

Naast ADE en QRE is er een derde discipline nodig:

```text
Operator Learning System
```

Dit hoeft geen softwarelaag te zijn. Het is een werkwijze waarmee lessons learned niet verdwijnen in losse chats.

Aanbevolen documenten:

```text
docs/operator/valkuilenregister.md
docs/operator/decision_journal_template.md
docs/operator/monthly_architecture_review.md
docs/operator/phase_premortem_template.md
```

## 6.2 Valkuilenregister

Elke bekende valkuil krijgt:

- ID;
- naam;
- symptoom;
- oorzaak;
- preventieve constraint;
- test;
- gate;
- voorbeeld uit project;
- status.

Voorbeelden:

| ID | Valkuil | Preventie |
|---|---|---|
| V-001 | Te vroeg naar strategieën | Geen strategy/preset work zonder behavior hypothesis |
| V-002 | Data als losse input behandelen | Source manifest + quality gates verplicht |
| V-003 | Governance achteraf repareren | Authority boundary per module |
| V-004 | Dashboard wordt control plane | Read-only first |
| V-005 | Autonomie verwarren met authority | May/May Not per laag |
| V-006 | Self-learning wordt black box | Alleen deterministic feedback metrics |
| V-007 | Backtest verwarren met evidence | Null model + OOS + cost gates |
| V-008 | Source count verwarren met source quality | Source usefulness ledger |
| V-009 | Feature bouwen zonder failure mode | Definition of Failure verplicht |
| V-010 | Scope creep via kleine refactor | One coherent unit per PR |

## 6.3 Phase pre-mortem

Voor elke fase:

```text
Stel dat deze fase over vier weken problematisch blijkt.
Wat zijn de vijf meest waarschijnlijke oorzaken?
```

Voor elke oorzaak:

- preventieve constraint;
- test;
- stop condition;
- observable output.

## 6.4 Decision journal

Voor elke grote keuze:

```text
Besluit:
Waarom nu:
Alternatieven:
Waarom niet gekozen:
Risico:
Wat doet ons later terugdraaien:
Metric die succes bewijst:
Metric die falen bewijst:
Reviewdatum:
```

## 6.5 Architecture reset

Elke maand:

- Welke laag heeft te veel verantwoordelijkheden gekregen?
- Welke artifact is stilletjes source of truth geworden?
- Welke workaround is beleid geworden?
- Welke module importeert te veel?
- Welke output begrijpt de operator niet meer?
- Welke test zegt niets meer?
- Waar ontstaat governance noise?

Scoreer:

| Dimensie | Score 1-5 | Opmerking |
|---|---:|---|
| Layer separation | | |
| Data quality confidence | | |
| Research reproducibility | | |
| Operator clarity | | |
| Governance noise | | |
| Throughput efficiency | | |
| Evidence quality | | |

---

# 7. De centrale strategie: van minimal loop naar trusted loop

## 7.1 Huidige minimal loop

De huidige QRE-loop ziet er conceptueel zo uit:

```text
hypothesis discovery
-> routing
-> sampling
-> controlled eval
-> policy diagnostics
-> screening attribution
-> decision state
-> action planner
-> synthesis gate
```

Deze loop is waardevol, maar nog niet automatisch trusted.

## 7.2 Trusted loop criteria

De loop is pas trusted als hij consequent kan beantwoorden:

1. Wat werd onderzocht?
2. Waarom werd dit onderzocht?
3. Welke data was toegestaan?
4. Welke source quality gold?
5. Welke hypothesis was actief?
6. Welke campaign/eval is uitgevoerd?
7. Welke policy filters zijn toegepast?
8. Waarom ontstond wel/geen candidate?
9. Welke failure class is vastgesteld?
10. Welke next action volgt?
11. Welke eerdere failures lijken hierop?
12. Mag synthesis wel/niet?
13. Is de conclusie reproduceerbaar?

## 7.3 Trusted loop metrics

Introduceer per run:

| Metric | Betekenis | Richting |
|---|---|---|
| unknown_failure_rate | Aandeel failures zonder concrete oorzaak | Omlaag |
| actionable_failure_rate | Aandeel failures met policy-action | Omhoog |
| attribution_depth_score | Hoe specifiek failure causes zijn | Omhoog |
| data_readiness_coverage | Hoeveel input is quality-gated | Omhoog |
| duplicate_suppression_rate | Herhaalde researchpaden voorkomen | Omhoog |
| synthesis_eligibility_rate | Hoe vaak synthesis toegestaan is | Contextafhankelijk |
| synthesis_block_reason_coverage | Hoe duidelijk synthesis-blokkades zijn | Omhoog |
| operator_explanation_completeness | Kan operator volgen waarom? | Omhoog |

---

# 8. Hoofdroute: van nu naar target state

## 8.1 Fase 0 - Freeze interpretation, not development

Doel:

```text
Voorkomen dat de bestaande minimal slices worden aangezien voor volwassen capabilities.
```

Acties:

- Maak een statusmatrix van alle huidige modules.
- Classificeer per module:
  - scaffold;
  - minimal capability;
  - production-ready research primitive;
  - operator-trusted;
  - policy-critical.
- Definieer per module de volgende maturity stap.

Voorbeeld:

| Module | Huidige status | Volgende maturity stap |
|---|---|---|
| screening_failure_attribution | minimal | unknown reduction + more classes |
| synthesis_gate | minimal | richer eligibility explanations |
| research_action_plan | minimal | action usefulness tracking |
| controlled_eval | minimal | artifact-backed eval lineage |
| hypothesis_discovery | minimal | data-readiness-aware seeds |

Deliverable:

```text
artifacts/governance/research_loop_maturity_latest.v1.json
```

## 8.2 Fase 1 - Unknown Failure Reduction Sprint

Doel:

```text
Verlaag unknown_screening_failure naar concrete, actiegerichte failure classes.
```

Waarom eerst:

De no-candidate diagnoseketen is net gebouwd. Nu moet hij bewijzen dat hij echte verklaringen produceert.

Nieuwe failure classes kunnen zijn, mits artifact evidence bestaat:

- missing_screening_evidence;
- incomplete_policy_trace;
- no_candidate_after_policy_filter;
- no_survivor_after_eval;
- insufficient_oos_window;
- missing_metric_field;
- unsupported_failure_shape;
- synthesis_gate_blocked;
- data_coverage_unknown;
- source_quality_unknown;
- identity_unresolved;
- null_model_not_available;
- policy_trace_inconsistent.

Belangrijke constraint:

```text
Geen causes verzinnen. Alleen classificeren op basis van bestaande evidence fields.
```

Deliverables:

- verbeterde attribution function;
- fixtures voor elke class;
- before/after report;
- operator-readable summary;
- next-action mapping per class.

Definition of Done:

- unknown rate daalt aantoonbaar;
- elke nieuwe class heeft testfixture;
- geen strategy/campaign behavior change;
- geen frozen contract mutation;
- report toont welke data ontbreekt als cause niet kan worden vastgesteld.

## 8.3 Fase 2 - Data Foundation als productlaag

Doel:

```text
Maak data quality, coverage, identity en cache readiness zichtbaar voordat research intelligence erop mag bouwen.
```

Subfases:

```text
v3.data.1 - Local Research Cache Manifest + Coverage Reporter
v3.data.2 - Source Quality Gates
v3.data.3 - Instrument Identity / Symbology
v3.data.4 - Parquet OHLCV Backfill
v3.data.5 - Feature / Diagnostic Panel Builder
v3.data.6 - Data Readiness Gate for Routing
```

Belangrijk:

```text
Dit is geen alpha-werk.
Dit is betrouwbaarheid onder de research loop.
```

## 8.4 Fase 3 - Research Memory en Retrieval

Doel:

```text
QRE moet eerdere hypotheses, campaigns, diagnostics, failures en policy actions kunnen terugvinden.
```

Bouwen:

- ontology;
- entity resolution;
- lineage;
- knowledge graph;
- deterministic keyword index;
- simple rank fusion;
- related-failure retrieval.

Eerste implementatie:

```text
SQLite/JSONL/FTS5 eerst.
Geen vector DB nodig als startpunt.
```

## 8.5 Fase 4 - Routing en sampling kalibreren

Doel:

```text
Routing/sampling moeten niet alleen bestaan, maar aantoonbaar betere research ordering leveren.
```

Routing moet meenemen:

- expected information gain;
- behavior orthogonality;
- prior failures;
- source quality;
- identity confidence;
- cache coverage;
- compute cost;
- dead-zone risk;
- data readiness.

Sampling moet meenemen:

- coverage;
- OOS availability;
- regime coverage;
- source agreement;
- null-model feasibility;
- feature panel availability;
- overfit risk.

## 8.6 Fase 5 - Observability operator-grade maken

Doel:

```text
De operator moet zonder code te lezen kunnen uitleggen waarom QRE iets deed.
```

Read-only surfaces:

- why explored;
- why failed;
- why blocked;
- why synthesis allowed/blocked;
- source quality;
- data readiness;
- previous similar failures;
- next action;
- policy gate path.

## 8.7 Fase 6 - Hypothesis Discovery verdiepen

Doel:

```text
Van minimal hypothesis seed naar behavior-first research front door.
```

Hypothesis Discovery mag:

- hypotheses voorstellen;
- expected research value scoren;
- campaign seeds voorstellen;
- feasibility checken;
- prior failures ophalen.

Hypothesis Discovery mag niet:

- executable strategy code schrijven;
- hidden alpha logic introduceren;
- direct candidate promotion doen;
- paper/shadow/live triggeren.

## 8.8 Fase 7 - Failure -> Action -> Reroute sluiten

Doel:

```text
Elke belangrijke failure moet een deterministic next-action of stop-action hebben.
```

Voorbeelden:

| Failure | Action |
|---|---|
| insufficient_trades | higher timeframe or broader sample |
| high_drawdown | volatility normalization or reject |
| weak_stability | regime segmentation |
| null_model_not_beaten | reject/demote |
| source_quality_failed | block source-derived seed |
| identity_unresolved | block escalation |
| high_entropy_false_positive | suppress directional mapping |
| quorum_insufficient | keep seed, no escalation |
| missing_metric_field | repair artifact/eval pipeline |

## 8.9 Fase 8 - Adaptive Research Learning

Doel:

```text
QRE leert van evidence zonder black box.
```

Allowed learning:

- behavior-family fitness;
- source usefulness;
- diagnostic utility;
- false-positive contribution;
- dead-zone recurrence;
- policy action outcomes;
- routing improvement metrics;
- failure recurrence reduction.

Not allowed:

- hidden ML selector;
- LLM strategy invention;
- RLAIF;
- live risk mutation;
- capital allocation;
- stochastic strategy mutation.

## 8.10 Fase 9 - Shadow

Doel:

```text
Real-time behavior validation zonder kapitaal.
```

Pas starten wanneer:

- candidate quality meaningful is;
- failure attribution betrouwbaar is;
- data readiness gates werken;
- research memory werkt;
- policy gates uitlegbaar zijn.

## 8.11 Fase 10 - Paper

Doel:

```text
Simulated capital deployment onder governance.
```

Voorwaarden:

- shadow parity;
- audit ledger;
- paper readiness gates;
- simulated risk layer;
- kill switch;
- no live broker path.

## 8.12 Fase 11 - Controlled Live

Doel:

```text
Tiny-capital, whitelisted, rollbackable live deployment.
```

Alleen met:

- explicit operator approval;
- whitelist;
- reconciliation;
- kill switches;
- risk envelope;
- deployment gates;
- rollback plan;
- post-live audit.

---

# 9. Data-throughput ontwerp

## 9.1 Probleemdefinitie

Het probleem is niet alleen dat er veel data nodig is. Het probleem is:

```text
Kan genoeg betrouwbare data goedkoop, reproduceerbaar en consistent door alle lagen heen stromen?
```

De keten moet zijn:

```text
source candidate
-> source manifest
-> raw snapshot
-> identity mapping
-> quality gates
-> normalized cache
-> feature/diagnostic panels
-> data readiness score
-> hypothesis discovery
-> routing/sampling
-> campaign/eval
-> evidence ledger
-> failure-to-action
-> source usefulness update
-> research memory update
```

## 9.2 Vier datalagen

Gebruik het model:

```text
Bronze  = raw source snapshots
Silver  = normalized + quality-gated data
Gold    = feature/diagnostic-ready panels
Platinum = evidence-ready campaign datasets
```

QRE-regel:

```text
Hypothesis discovery mag pas vanaf Gold.
Evidence/policy mag pas vanaf Platinum.
```

## 9.3 Aanbevolen technische stack

Aanbevolen stack:

```text
Python       = orchestration, policy, artifacts, tests
Polars       = snelle dataframe transforms
DuckDB       = analytics/query over Parquet
Parquet      = kolomopslag en snapshots
SQLite/FTS5  = research memory en deterministic retrieval
Pydantic/dataclasses = schema discipline
pytest       = behavior/architecture tests
Rust later   = alleen bewezen hot paths
```

Niet nu:

- Spark;
- Kafka;
- Airflow;
- Ray;
- Dask;
- full cloud warehouse;
- volledige Rust rewrite;
- vector DB als eerste stap.

Waarom niet:

```text
Infra-complexiteit mag niet sneller groeien dan evidence quality.
```

## 9.4 Data lake structuur

Aanbevolen structuur:

```text
data_lake/
  raw/
    binance/
    bitvavo/
    yahoo/
    fred/
  normalized/
    crypto_ohlcv/
    equities_ohlcv/
    macro_daily/
  features/
    returns/
    volatility/
    entropy/
    tails/
    state_transitions/
    null_models/
  panels/
    crypto_1h_core_panel/
    crypto_4h_core_panel/
    equities_daily_core_panel/
  manifests/
    cache_manifest_latest.v1.json
    cache_coverage_latest.v1.json
    cache_quality_latest.v1.json
```

## 9.5 Dataset passport

Elke dataset krijgt een passport:

```json
{
  "dataset_id": "crypto_ohlcv_bitvavo_btc_eur_1h_2024",
  "source_id": "bitvavo_public_candles",
  "instrument_id": "crypto:btc-eur",
  "timeframe": "1h",
  "raw_snapshot_hash": "...",
  "normalized_snapshot_hash": "...",
  "schema_version": "ohlcv.v1",
  "quality_gates": {
    "freshness": "PASS",
    "missing_data": "PASS",
    "duplicates": "PASS",
    "outliers": "WARN",
    "source_agreement": "PASS",
    "identity_mapping": "PASS"
  },
  "allowed_for": {
    "hypothesis_discovery": true,
    "routing": true,
    "campaign_eval": true,
    "evidence_policy": true,
    "paper_readiness": false
  }
}
```

Zonder passport geen automatische research.

## 9.6 Data readiness score

Voor elke asset/timeframe/source:

```json
{
  "instrument_id": "crypto:btc-eur",
  "source_id": "bitvavo_public_candles",
  "timeframe": "1h",
  "coverage_score": 0.91,
  "freshness_score": 0.98,
  "missing_data_score": 0.96,
  "identity_confidence": 1.0,
  "source_agreement_score": 0.88,
  "research_ready": true,
  "blocked_reason": null
}
```

Routing mag data readiness gebruiken als input, maar data readiness is geen alpha.

## 9.7 Terugwerkende kracht

Oude runs hoeven niet weggegooid te worden. Ze moeten worden ingelezen als legacy context:

```text
legacy_run
unknown_source_quality
unknown_identity_confidence
not_reproducible
usable_for_operator_context_only
excluded_from_policy_learning
```

Daarmee behoud je historische leerwaarde zonder oude resultaten te veel authority te geven.

## 9.8 Historical evidence rebuild

Bouw een ingestor:

```text
research/history/historical_run_ingestor.py
```

Taken:

- oude artifacts lezen;
- hypothesis records maken;
- campaign records maken;
- evidence records maken;
- failure records maken;
- source lineage waar mogelijk koppelen;
- unknown/legacy flags zetten;
- oude runs uitsluiten van policy-learning als datakwaliteit onbekend is.

## 9.9 Feature panels

Zware features moeten herbruikbaar worden:

```text
features bestaan al
campaign leest feature panel
campaign test alleen hypothese
```

Voorbeelden:

- returns panel;
- volatility state panel;
- entropy state panel;
- tail risk panel;
- state transition panel;
- source quality panel;
- identity quality panel;
- event context panel.

---

# 10. Research memory ontwerp

## 10.1 Waarom research memory cruciaal is

Zonder research memory lijkt QRE autonoom, maar herhaalt het dezelfde fouten.

Met research memory kan QRE zeggen:

```text
Deze hypothese lijkt op drie eerdere failures.
Die faalden door high_entropy_false_positive en null_model_not_beaten.
Dus eerst regime segmentation of null challenge, niet opnieuw brute force.
```

## 10.2 Core entities

Minimale entities:

- Instrument;
- Source;
- Dataset;
- Behavior;
- Hypothesis;
- Diagnostic;
- Campaign;
- EvalRun;
- Evidence;
- Failure;
- PolicyAction;
- Candidate;
- OperatorDecision.

## 10.3 Core edges

Voorbeelden:

```text
Hypothesis USES_SOURCE Source
Hypothesis TESTS_BEHAVIOR Behavior
Campaign TESTS Hypothesis
EvalRun PRODUCES Evidence
Evidence SUPPORTS Hypothesis
Evidence CONTRADICTS Hypothesis
Failure TRIGGERS PolicyAction
Source PRODUCED Dataset
Dataset HAS_QUALITY DataQuality
Campaign USED Dataset
PolicyAction SUPPRESSES BehaviorFamily
```

## 10.4 Eerste implementatie

Gebruik eerst:

- JSONL voor append-only records;
- SQLite voor index;
- FTS5 voor keyword retrieval;
- deterministic rank fusion;
- artifact exports naar JSON.

Nog geen zware graph database nodig.

## 10.5 Retrieval use cases

- Zoek eerdere failures voor nieuwe hypothese.
- Zoek vergelijkbare campaigns.
- Zoek eerdere source issues.
- Zoek policy actions na vergelijkbare failures.
- Zoek behavior family history.
- Zoek contradictory evidence.
- Zoek duplicate hypotheses.

---

# 11. Governance en authority model

## 11.1 May / May Not per laag

Elke module moet een May / May Not sectie hebben.

Voorbeeld diagnostics:

May:

- research routing beinvloeden;
- sampling context leveren;
- evidence scoring ondersteunen;
- cooldown adviseren;
- observability voeden.

May Not:

- trades plaatsen;
- candidates promoten;
- live risk muteren;
- frozen contracts wijzigen;
- policy gates omzeilen.

Voorbeeld retrieval:

May:

- context vinden;
- prior failures ophalen;
- duplicate hypotheses signaleren;
- operator explanations ondersteunen.

May Not:

- deployment ranken;
- evidence policy vervangen;
- candidates autoriseren;
- trades selecteren.

## 11.2 One-way door versus two-way door

Two-way door:

- read-only report;
- sidecar artifact;
- docs;
- unit test;
- non-critical schema.

One-way door:

- frozen contract change;
- live execution path;
- broker integration;
- risk engine mutation;
- dashboard mutation route;
- auto-merge expansion;
- hidden selector.

Regel:

```text
Two-way door: kleine PR, snel leren.
One-way door: ADR, pre-mortem, operator approval, rollback plan.
```

## 11.3 Architecture tests

Niet alleen unit tests. Ook architecture tests:

- diagnostics importeren geen broker modules;
- research modules schrijven niet naar live/paper paths;
- frontend bevat geen research business logic;
- frozen contracts blijven ongewijzigd;
- source-derived hypotheses zonder quality gate worden geblokkeerd;
- campaign zonder hypothesis_id faalt;
- failure zonder failure_code faalt;
- dataset zonder manifest kan niet naar evidence-ready;
- Addendum reference-only betekent geen active queue items.

---

# 12. Concrete implementatiepromptbibliotheek

## 12.1 Prompt - Unknown Failure Reduction Sprint

```text
You are working in the QRE repository.

Active phase:
v3.16.x - Unknown Screening Failure Reduction Sprint

Goal:
Reduce unknown_screening_failure by adding deterministic, evidence-backed sub-classifications to the current no-candidate/screening attribution pipeline.

Context:
The current system already has controlled eval, no-candidate diagnostics, research decision state, research action planner, policy filter diagnostics, screening failure attribution and synthesis eligibility gate. The next step is not adding more layers, but making the attribution chain more actionable.

Hard constraints:
- Do not modify strategy logic.
- Do not modify campaign execution behavior.
- Do not mutate research_latest.json or strategy_matrix.csv.
- Do not touch live/paper/shadow/risk/broker/execution paths.
- Do not invent causes unsupported by artifacts.
- Write sidecar/reporting artifacts only.

In scope:
- inspect current screening evidence artifacts;
- identify why observations fall into unknown_screening_failure;
- add deterministic classifications where evidence fields support them;
- add tests/fixtures for each class;
- produce before/after attribution report;
- map each class to an operator-readable next action.

Candidate classes if supported:
- missing_screening_evidence
- incomplete_policy_trace
- no_candidate_after_policy_filter
- no_survivor_after_eval
- insufficient_oos_window
- missing_metric_field
- unsupported_failure_shape
- synthesis_gate_blocked
- data_coverage_unknown
- source_quality_unknown
- identity_unresolved
- null_model_not_available
- policy_trace_inconsistent

Validation:
- targeted unit tests;
- fixture coverage for every new class;
- no frozen contract changes;
- protected/execution paths untouched;
- report shows unknown count before and after.

Definition of Done:
- unknown failure rate is materially reduced or explicitly explained as not reducible with current artifacts;
- no unsupported attribution is introduced;
- every class is actionable;
- final handoff includes next recommended research action.
```

## 12.2 Prompt - Data Foundation v3.data.1

```text
Active phase:
v3.data.1 - Local Research Cache Manifest + Coverage Reporter

Goal:
Introduce a read-only local research cache manifest and coverage reporting layer so QRE can measure what data is available before routing, sampling or hypothesis discovery depends on it.

In scope:
- cache manifest schema;
- coverage reporter;
- read-only artifact writer;
- deterministic tests;
- fixture-based coverage examples;
- no live data fetching unless existing fixtures are already present.

Out of scope:
- new strategies;
- campaign execution changes;
- paper/shadow/live/risk/broker/execution paths;
- dashboard mutation routes;
- source adapters beyond manifest representation;
- frozen contract mutation.

Expected files:
- research/cache/__init__.py
- research/cache/cache_manifest.py
- research/cache/coverage_report.py
- tests/unit/test_cache_manifest.py
- tests/unit/test_cache_coverage_report.py

Expected artifacts:
- artifacts/cache/cache_manifest_latest.v1.json
- artifacts/cache/cache_coverage_latest.v1.json

Definition of Done:
- cache entries have source, instrument, timeframe, schema version, row count, min/max timestamp and content hash;
- coverage report groups by source/instrument/timeframe;
- missing coverage is visible;
- no research policy consumes cache yet;
- tests prove deterministic output.
```

## 12.3 Prompt - Data Foundation v3.data.2

```text
Active phase:
v3.data.2 - Source Quality Gates

Goal:
Add deterministic source quality gates so external/source data cannot become research context without manifest-backed quality checks.

In scope:
- source manifest schema;
- quality gate definitions;
- freshness, missing data, timestamp monotonicity, duplicate observation, outlier and coverage checks;
- source quality report artifact;
- tests with pass/warn/fail cases.

Out of scope:
- automated source fetching;
- paid data;
- live data trading;
- hypothesis promotion;
- strategy changes;
- frozen contract mutation.

Definition of Done:
- every quality gate has a closed result vocabulary;
- failed source quality blocks research-ready status;
- report is operator-readable;
- tests prove fail-closed behavior.
```

## 12.4 Prompt - Research Memory v1

```text
Active phase:
Research Memory v1 - Hypothesis, Campaign, Evidence and Failure Lineage

Goal:
Create a deterministic research memory scaffold so QRE can retrieve prior hypotheses, failures, campaigns and policy actions before proposing or routing new research.

In scope:
- append-only JSONL record schemas;
- simple ontology for behavior/failure/policy/action types;
- lineage artifact writer;
- SQLite/FTS5 keyword index if repo constraints allow;
- deterministic retrieval of similar prior failures;
- tests for duplicate suppression and lineage export.

Out of scope:
- vector DB;
- graph ML;
- hidden ranking;
- candidate promotion;
- live/paper/shadow/risk/broker/execution paths.

Definition of Done:
- a new hypothesis can be linked to prior failures;
- retrieval returns explainable context IDs;
- duplicate hypothesis warning can be emitted;
- artifacts are sidecars;
- frozen contracts untouched.
```

---

# 13. KPI framework

## 13.1 Project-level KPIs

| KPI | Doel | Waarom |
|---|---|---|
| Unknown failure rate | Omlaag | Minder blind spots |
| Actionable failure rate | Omhoog | Failures worden bruikbaar |
| Data readiness coverage | Omhoog | Betrouwbare input |
| Source quality fail-closed rate | Omhoog waar nodig | Slechte data blokkeren |
| Duplicate research suppression | Omhoog | Minder verspilde compute |
| Operator explanation completeness | Omhoog | Grip behouden |
| CI/governance stability | Hoog | ADE betrouwbaar |
| Scope drift incidents | Omlaag | Architectuurdiscipline |
| Frozen contract violations | Nul | Output contracts stabiel |
| Protected path violations | Nul | Safety |

## 13.2 QRE research KPIs

| KPI | Definitie |
|---|---|
| hypothesis_seed_quality | Aandeel seeds met data readiness, prior context en feasibility |
| eval_lineage_completeness | Aandeel evals met volledige hypothesis->campaign->evidence lineage |
| null_model_challenge_coverage | Aandeel candidates/hypotheses met null comparison |
| policy_filter_explainability | Aandeel policy blocks met concrete reason code |
| synthesis_gate_explainability | Aandeel synthesis decisions met clear allow/block reason |
| failure_to_action_coverage | Aandeel failures met deterministic next action |

## 13.3 ADE KPIs

| KPI | Definitie |
|---|---|
| eligible_unit_selection_accuracy | Next-buildable unit is echt veilig en relevant |
| authority_classification_precision | Geen unsafe unit als safe classificeren |
| operator_inbox_noise | False positives omlaag |
| PR final report completeness | Elke run eindigt met bruikbaar report |
| CI green rate | Stabiliteit van conveyor |
| scope containment | PR wijkt niet af van unit |

---

# 14. Risicoregister

## 14.1 Toprisico's

| Risico | Impact | Preventie |
|---|---|---|
| Minimal slices worden overschat | Hoog | Maturity matrix |
| Unknown failures blijven groot | Hoog | Unknown Failure Reduction Sprint |
| Data pipeline versnelt slechte data | Zeer hoog | Quality gates + data passport |
| ADE krijgt te veel authority | Zeer hoog | Authority classifier + no-touch tests |
| Addenda worden te vroeg geactiveerd | Hoog | Reference-only status respecteren |
| Dashboard krijgt mutation controls te vroeg | Hoog | Read-only first |
| Self-learning wordt black-box | Zeer hoog | Deterministic feedback only |
| Strategy synthesis start te vroeg | Hoog | Synthesis eligibility gate streng houden |
| Historical runs krijgen te veel authority | Middel/hoog | Legacy flags, exclude from policy learning |
| Rust/infra rewrite leidt af | Middel | Alleen na measured bottleneck |

## 14.2 Stop conditions

Stop een fase als:

- frozen contracts wijzigen zonder expliciete approval;
- live/paper/shadow/risk/broker paths worden geraakt buiten scope;
- tests worden verzwakt;
- cause attribution wordt verzonnen zonder artifact evidence;
- source quality fail-open werkt;
- dashboard mutation route wordt toegevoegd zonder governance phase;
- strategy code wordt gegenereerd door hypothesis discovery;
- operator explanation ontbreekt voor policy-critical output.

---

# 15. Beslisregels voor technologie

## 15.1 Wanneer Python genoeg is

Python is genoeg voor:

- orchestration;
- artifacts;
- policy logic;
- report generation;
- hypothesis schemas;
- failure mappings;
- governance classifiers;
- unit tests;
- small/medium diagnostics.

## 15.2 Wanneer Polars/DuckDB nodig is

Gebruik Polars/DuckDB voor:

- grote OHLCV panels;
- batch feature generation;
- coverage scans;
- source agreement checks;
- multi-asset diagnostics;
- query over Parquet;
- reducing pandas bottlenecks.

## 15.3 Wanneer Rust zinvol wordt

Rust pas overwegen als:

- profiling aantoont dat Python/Polars/DuckDB onvoldoende is;
- dezelfde hot loop vaak draait;
- bottleneck CPU-bound is;
- interface stabiel is;
- testfixtures volwassen zijn.

Mogelijke Rust-kandidaten later:

- null-model simulations;
- state transition matrix generation op grote panels;
- tick/1m feature generation;
- shadow low-latency parity checks.

Niet in Rust herschrijven:

- policy;
- routing explainability;
- governance;
- artifact schemas;
- operator reports.

## 15.4 Wanneer geen nieuwe infra

Geen Spark/Kafka/Airflow/Ray/Dask zolang:

- single-machine DuckDB/Polars niet gemeten tekortschiet;
- data quality gates nog niet volwassen zijn;
- research memory nog niet stabiel is;
- operator observability nog niet goed genoeg is.

---

# 16. Implementatieritme

## 16.1 Elke fase als capability unit

Elke fase moet opleveren:

1. nieuwe capability;
2. input artifact;
3. output artifact;
4. quality gate;
5. failure mode;
6. observability;
7. tests;
8. authority boundary;
9. final report.

## 16.2 Capability template

```text
Capability name:
Problem solved:
Input artifacts:
Output artifacts:
Authority boundary:
Allowed decisions:
Forbidden decisions:
Failure modes:
Tests:
Operator surface:
Definition of Done:
Definition of Failure:
Known limitations:
Next capability dependency:
```

## 16.3 Sprint cadence

Aanbevolen cadence:

- 1 sprint = 1 capability family;
- maximaal 3-5 PRs per sprint;
- elke PR klein en coherent;
- na elke sprint: maturity matrix update;
- na elke sprint: operator summary;
- na elke sprint: lessons learned update.

---

# 17. De eerste 10 concrete stappen

## Stap 1 - Research loop maturity matrix

Maak zichtbaar welke huidige modules scaffold/minimal/trusted zijn.

## Stap 2 - Unknown Failure Reduction Sprint

Reduceer onbekende failures en maak causes actiegericht.

## Stap 3 - Synthesis gate calibration

Zorg dat synthesis eligibility niet alleen blokkeert, maar uitlegt:

- welke precondition ontbreekt;
- welke artifact ontbreekt;
- welke researchactie nodig is;
- wanneer opnieuw proberen zinvol is.

## Stap 4 - Data cache manifest

Zonder data fetching, eerst zichtbaarheid.

## Stap 5 - Source quality gates

Maak fail-closed source readiness.

## Stap 6 - Identity/symbology gate

Block ambiguous instrument identity.

## Stap 7 - Historical run ingestor

Oude runs importeren als legacy context.

## Stap 8 - Research memory v1

Hypotheses, campaigns, evidence, failures en policy actions linkbaar maken.

## Stap 9 - Routing calibration

Routing scoren op evidence value, not preset count.

## Stap 10 - Operator-grade observability

Een operator moet de loop kunnen volgen zonder code.

---

# 18. Wat voorlopig bewust niet doen

Niet doen in de komende korte fase:

- live/paper/shadow uitbreiden;
- broker adapters;
- risk engine changes;
- capital allocation;
- dashboard mutation routes;
- full Addendum 1/2/3 activation;
- paid data feeds;
- GNN/HMM/transformer price prediction;
- RLAIF;
- genetic programming;
- stochastic strategy mutation;
- Rust rewrite;
- vector DB als kern;
- social scraping;
- source count maximaliseren;
- strategy synthesis zonder strict eligibility.

Waarom:

```text
De huidige bottleneck is niet te weinig ambitie.
De bottleneck is trust in de minimal loop.
```

---

# 19. Target operating model

## 19.1 Dagelijkse workflow

```text
1. Inspect latest artifacts
2. Check unknown failures
3. Check data readiness changes
4. Check active next actions
5. Check ADE queue health
6. Pick only the next eligible capability unit
7. Execute via branch/PR/CI/final report
8. Update maturity and lessons learned
```

## 19.2 Wekelijkse workflow

```text
1. Generate weekly build summary
2. Classify ADE vs QRE work
3. Map commits to roadmap/maturity
4. Identify scaffolds promoted to capabilities
5. Identify unknowns and blockers
6. Update roadmap scope status
7. Decide next sprint theme
```

## 19.3 Maandelijkse workflow

```text
1. Architecture reset
2. Valkuilenregister update
3. Decision journal review
4. Data debt review
5. Source usefulness review
6. Research loop trust review
7. Operator cognitive load review
```

---

# 20. Eindbeeld per maturity laag

## 20.1 v3.x - Research intelligence

QRE kan:

- hypotheses voorstellen;
- data readiness checken;
- routing/sampling bepalen;
- campaigns evalueren;
- failures verklaren;
- next actions plannen;
- learning metrics bijhouden.

Nog niet:

- real-time deployment;
- paper capital;
- live capital;
- autonomous strategy code writing.

## 20.2 v4.x - Shadow

QRE kan:

- realtime signal parity checken;
- timing drift meten;
- shadow decisions loggen;
- execution realism voorbereiden;
- no-capital live-like validation doen.

Nog niet:

- paper orders;
- live orders;
- capital allocation.

## 20.3 v5.x - Paper

QRE kan:

- simulated orders;
- paper lifecycle;
- simulated risk;
- performance degradation;
- portfolio paper behavior.

Nog niet:

- real capital.

## 20.4 v6.x - Controlled live

QRE kan alleen onder strikte governance:

- tiny capital;
- whitelist;
- risk envelope;
- kill switches;
- reconciliation;
- rollback;
- operator approval.

---

# 21. Slotadvies

De verleiding na de laatste build summary is om te zeggen:

```text
We hebben de lagen nu, dus door naar de volgende laag.
```

Dat zou te vroeg zijn.

De juiste conclusie is:

```text
We hebben nu genoeg skelet om de echte bottleneck te testen:
kan QRE verklaren waarom research niet tot candidates leidt,
en kan QRE betere vervolgstappen kiezen op basis van evidence?
```

Daarom is de beste volgende beweging:

```text
Van meer bouwen naar beter kalibreren.
Van scaffolds naar trusted capabilities.
Van unknown failures naar actionable failures.
Van losse data naar data passports.
Van historical artifacts naar research memory.
Van operator-intuitie naar operator-governed autonomous research.
```

De target state is haalbaar, maar alleen als elke stap voldoet aan deze regel:

```text
Geen extra autonomie zonder extra explainability.
Geen extra throughput zonder extra data quality.
Geen extra learning zonder failure memory.
Geen extra execution zonder governance.
```

Dat is de how.

---

# Appendix A - Compacte roadmap

```text
A. Stabilize current minimal loop
B. Unknown Failure Reduction Sprint
C. Synthesis Gate Calibration
D. Data Foundation v3.data.1-6
E. Historical Evidence Rebuild
F. Research Memory v1
G. Routing/Sampling Calibration
H. Operator-grade Observability
I. Hypothesis Discovery v2
J. Failure -> Action -> Reroute Loop
K. Adaptive Research Learning Metrics
L. Shadow Readiness
M. Paper Readiness
N. Controlled Live Readiness
```

# Appendix B - Definition of Done voor elke toekomstige fase

Elke fase is pas klaar als:

- scope compleet is;
- tests groen zijn;
- behavior gevalideerd is;
- frozen contracts intact zijn;
- protected paths untouched zijn;
- output artifacts valide zijn;
- operator explanation bestaat;
- known limitations gedocumenteerd zijn;
- final report compleet is;
- next action expliciet is.

# Appendix C - De belangrijkste regel

```text
Het doel is niet dat QRE meer doet.
Het doel is dat QRE beter weet wat het wel en niet moet doen.
```
