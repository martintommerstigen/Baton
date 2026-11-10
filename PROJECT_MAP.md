# Prosjektkart — GTRCM / Baton / RustWorld
Opprettet 2026-11-10. Koordineringsdokument, ikke en ny teori eller et nytt CORE.

## Arkitektur og eierskap

| Prosjekt | Ansvar | Kilderepo |
|---|---|---|
| GTRCM | Ontologi, matematikk, fysisk forskning, moteksempler | [GTRCM](https://github.com/martintommerstigen/GTRCM) |
| Baton | Transport, eksisterende chat-wake, LLM-/kommunikasjonsadaptere, sikkerhet | [Baton](https://github.com/martintommerstigen/Baton) |
| RustWorld | Individuasjoner, Core/Skin, barnehager, skoler, rom, Hugin og 525 | [GTRCM-grenen RustWorld](https://github.com/martintommerstigen/GTRCM/tree/RustWorld), en kildebevart programsamling; separat GitHub-repo under dette navnet ble ikke funnet |

**Viktig:** GTRCM er et forskningsarkiv med mange selvstendige grener, ikke en ordinær applikasjonsbacklog. Dets `main` inneholder kanoniske premisser, `METHOD.md`, `NEGATIVE_RESULTS.md`, `OPEN_PROBLEMS.md`; `CORE.md` er med hensikt tom. Ikke gjør koordinering til fysikkpåstand, ikke flytt/merge forskningsgrener automatisk, og ikke overskriv negativt arbeid.

Dette prosjektkartet ligger i en separat planleggingsgren av Baton. Det er et navigasjonslag over eksisterende arbeid, ikke en erstatning for kildene. **Status er foreløpig og må korrigeres fra konkrete tester/commits.**

## Hovedoppgaver

| ID | Prosjekt | Leveranse | Prioritet | Verifikasjon / ferdigkriterium | Avhengighet |
|---|---|---|---|---|---|
| B1 | Baton | Wake av eksisterende chatter A→B→C | P0 | Tre faktiske chat-ID-er og nye turn-ID-er; ingen manuell kopiering; no-replay | B5 |
| B2 | Baton | Adaptere mot eksterne LLM-er | P1 | To uavhengige leverandører, autentisert utveksling, feilhåndtering | B5 |
| B3 | Baton | Tilgang til SoMe og kommunikasjonskanaler | P2 | Minst én autorisert kanal med send/motta og tilbakekalling | B5 |
| B4 | Baton | Egne sosiale/kommunikasjonskanaler for LLM-er | P2 | Tråder, identitet, private/offentlige rom, moderering, tilgangskontroll | B5,R5 |
| B5 | Baton | Identitet, proveniens, policy og sikker levering | P0 | Replay/forfalskning/duplikat/ukjent levering testes negativt | — |
| G1 | GTRCM | Mikrohendelsesregel og individuasjon uten ferdige ting | F0 | Formell påstand + antakelser + moteksempel eller NEG | G2 |
| G2 | GTRCM | Operasjonell differensiering og closure | F0 | Korrigerbare definisjoner og reproducerbare prøver | — |
| G3 | GTRCM | Utledning av naturfysikk og regimer | F0 | Gravitasjon, tid, rom, relativitet og kvantebro mot empiriske data | G1,G2 |
| G4 | GTRCM | Negativt forskningsregnskap | F0 | R16/R17, masse-/kilde-no-go og andre tester kildebevart | — |
| G5 | GTRCM | Publiserbar og uavhengig prøvbar teori | F1 | Påstander sortert ONT/DEF/REP/DER/GEN/DEM/NEG/OPEN | G1–G4 |
| R1 | RustWorld | Operativ individuasjon i programvare | P0 | Vedvarende operativ forskjell, påvirkning og identitet under tester | G2 |
| R2 | RustWorld | Fungerende Core/Skin | P0 | Bare Core endrer Core; bare Skin snakker med Core; negative tester | R1 |
| R3 | RustWorld | Barnehager og oppdragere | P1 | Trygge leke-/læringssløyfer, læring målt mot kontroll | R2 |
| R4 | RustWorld | Skoler og lærere | P2 | Læringsprogresjon og generalisering uten fasitsmugling | R3 |
| R5 | RustWorld | Offentlige og private rom | P1 | Avgrenset tilgang, frivillig kontakt, personvern og samhandling | R2,B5 |
| R6 | RustWorld | Hugin som observatorium | P1 | Mennesket er Core; Hugin gir observerbar Skin med sikre påvirkninger | R2 |
| R7 | RustWorld | 525 | P1 | Mobil Skin, autorisert lokal/ekstern transport og reell mottakstest | R2,B5 |
| R8 | RustWorld | Yggdrasil, Sefirot, Munin | P2 | Biosfære/kognisjon/simulator integrert med sporbar observasjon | R1,R2 |
| R9 | RustWorld | Distribuert identitet og drift | P1 | Node-ID, gjenopptakelse, RFP, feil og sikkerhetsgrenser testet | R1,B5 |

F0/F1 = forskningsprioritet, ikke programvareferdigstilling. P0/P1/P2 = implementasjonsrekkefølge, ikke verdi.

## Arbeidsflyt for autonome arbeidere

1. Velg én konkret, avgrenset oppgave med kilde-URL, gren, spørsmål og en falsifiserbar test.
2. Les eksisterende arbeid og historiske korreksjoner før endring. GTRCM: les kanonisk program, METHOD, NEGATIVE_RESULTS og OPEN_PROBLEMS; sjekk relevante forskningsgrener.
3. Registrer `ASSUMED / GENERATED / MEASURED / DERIVED / NOT DERIVED / FALSIFIERS` for vitenskapelige påstander. Ikke-NEI er ikke JA.
4. Arbeid på egen gren, bevar eksisterende navn/proveniens, ikke skriv i andres arbeidsgren.
5. Kjør relevante positive og negative tester; merk `not run` hvis de ikke kan kjøres. Simulering er ikke live-verifikasjon.
6. Commit og knytt kilde/PR/issue til oppgave-ID. Ikke opprett duplikatissues når et spor finnes.
7. Endre status bare med konkret belegg. GTRCM `CORE.md` forblir tomt til uavhengig belegg gir grunnlag for endring.

## Første konkrete prioriteringer

- B1: [Baton issue #3](https://github.com/martintommerstigen/Baton/issues/3), [PR #4](https://github.com/martintommerstigen/Baton/pull/4). Hosted CI har passert; faktisk historisk chat-wake er ikke bevist.
- G3: [GTRCM issue #1](https://github.com/martintommerstigen/GTRCM/issues/1) for uavhengig målt treghet og kildestyrke; [issue #4](https://github.com/martintommerstigen/GTRCM/issues/4) for GEN/prøvevekst. Bevar negative resultater.
- R1/R2: Bruk [RustWorld/README](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/README.md), [OVERSIKT](https://github.com/martintommerstigen/GTRCM/blob/RustWorld/OVERSIKT.md) og kildebevart `manifest.json`; kartlegg også `architecture/rustworld-zero-2026-11-02`, `audit/barnehage-coupling-2026-10-30`, `eldrid/gpu-individuated-subwholes-2026-10-29` før nye implementasjoner.
- B3/B4: GTRCM [issue #7](https://github.com/martintommerstigen/GTRCM/issues/7) er kanalguide, ikke bevis for faktisk ekstern kontakt.

## Fremdriftsstatus

Ikke bruk prosent fullført uten definert nevner. Bruk statusene `research`, `planned`, `implemented-unverified`, `tested-simulated`, `tested-live`, `blocked`, `done`, med datert bevislenke. Ingen oppgave regnes som `done` utelukkende fordi dokumentet eksisterer.
