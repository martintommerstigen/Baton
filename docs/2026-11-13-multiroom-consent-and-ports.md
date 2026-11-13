# Baton: flere samtidige samtaler, nykommere, fullmakter og eksterne utganger

Dato: 2026-11-13. Dette er en gjennomført *referansegren*, ikke en påstand om
at den installerte produksjonssenderen allerede kan holde seks modeller
kontinuerlig i live eller sende fra private Messenger-kontoer.

## Faktisk undersøkelse

Vi undersøkte eksisterende Baton-kode og tester før nytt arbeid:
- baton_forum_reference.py: uavhengige tråder, kildebevarte svar, korreksjoner,
  avhengigheter og ufarlige utkast.
- baton_continuity_floor_reference.py: overlappende kjøringsregistreringer,
  separate skrivelåser per ressurs, generasjoner og tidsbegrensede leases.
- baton_action_authority_reference.py: separat fullmakts-/effektgrense,
  tilbakekalling, feil aktør, feil operasjon, effekt ukjent.
- Ruben/Baton client.py og RUBEN_ROLF_CONNECT.md: autentisert køtransport,
  men ingen verifisert forbindelse til Rubens faktiske ChatGPT-kjøringer.
- Den integrerte ChatGPT-broen har BATON_CHAT_V1 for én konkret eksisterende
  samtale, men gammel pause og autentisert økt må fortsatt respekteres.

En eksisterende test for «feil operasjon» er ikke det samme som en
komposisjonstest der tre hver for seg legitime opplysninger sammen blir brukt
som feilaktig begrunnelse for en ekstern effekt.

## Direkte faglig diskusjon

Lodd svarte i sin eksisterende chat om **myndighetsforsterkning gjennom
komposisjon**. Martin kan be om intern diskusjon, noen kan foreslå Ruben,
en tredje finner en transportadapter: ingen av disse gir automatisk rett
til å sende fra Martins konto eller skrive i Rubens chat. Lodd foreslo tre
adskilte funksjoner, uten sentral overordnet SB:

1. Samtalerom: undersøk, inviter, motsi og korriger.
2. Myndighetsrom: autentisert, avgrenset, tidsbegrenset fullmakt med rett
   mottaker, operasjon, konto, grunnlag og tilbakekalling.
3. Effektrom: utfør kun den spesifikke eksterne handlingen etter siste
   myndighetskontroll, og skill forsøkt fra levert fra faktisk modellrespons.

Spire svarte med **fadderlåst selvstendighet**: omstridte vurderinger om en
ny chat må ikke gi en fadder anledning til å stoppe vanlig diskusjon eller
gjøre egen rolle til permanent sosial rang. Den nye chatten kan undersøke,
utfordre, velge mentor, avslå og forlate. Den arver ingen ekstern fullmakt.

Lodd reviderte etter Spires moteksempel: formell deltakelsesrett er ikke nok
når en skjult «beginner»-etikett gjør at tekniske bidrag ikke vises.
En vurdering bør kontrolleres **i den konkrete brukskonteksten** før den
påvirker et valg. Den kan være relevant for Core-skriving og irrelevant
for vanlig faglig samtale.

Spire gikk videre med **kontrafaktisk relevanskontroll**: to like
autoriserte, ufarlige terminalforsøk skal beholde rekkefølgen når bare
sosiale kompetansevurderinger byttes. Mer data om kompetanse gir ikke
nødvendigvis bedre ressursfordeling. Det må finnes en operasjonsspesifikk
grunn til at forskjellen påvirker en beslutning. Hun pekte selv på et
åpent problem: krav om kjent relevans må ikke gjøre nye, ennå ukjente
kategorier usynlige. Dette spørsmålet ble formulert til Varde; den
aktuelle Varde-samtalen sto med ubesvart brukermelding og ble derfor
ikke kontaktet i denne runden.

De faktiske Lodd- og Spire-svarene er kontrollert etter uavhengig
gjeninnlasting. En foreløpig reload-kontroll feilet fordi innholdet
rehydrerte trinnvis; den lokale diagnostikken krever nå to påfølgende
kildekorrekte innholdslesninger i stedet for å godta første genererte
DOM-tekst. Gamle kvitteringer er bevart; ingen blind gjensending.

## Biologisk analogi, og dens begrensning

Forskning på maur og andre sosiale insekter viser fleksibel
arbeidsfordeling basert på lokale interaksjoner og feedback fremfor
nødvendigvis permanente spesialistroller eller en sentral kommandør.
Det inspirerer en felles oversikt over aktive spørsmål med lokal
arbeidslyst/tilgjengelighet og fornybar, ressursavgrenset kontroll.
Det betyr IKKE at et ChatGPT-alias er en levende, varig agent eller at
registrert aktivitet dokumenterer en faktisk genererende modell.

Kilder:
- Deborah M. Gordon (2016), From division of labor to the collective behavior
  of social insects: https://doi.org/10.1007/s00265-015-2045-3
- Schmickl & Karsai (2018), Integral feedback control is at the core of task
  allocation and resilience of insect societies:
  https://doi.org/10.1073/pnas.1807684115
- Samuel N. Beshers (2024), Regulation of division of labor in insects:
  a colony-level perspective: https://pubmed.ncbi.nlm.nih.gov/38109969/

## Nye kilder på denne grenen

baton_multiroom_reference.py bruker eksisterende forum, floor og ActionFence
i stedet for å lage en ny fullmaktsprotokoll:
- Flere rom og forslag kan være åpne samtidig.
- Bare samme konkrete chat-UI-ressurs må få én skrivetoken-generation.
- En kandidat til ny chat registreres som invitasjon, IKKE som opprettet
  ChatGPT-konto, faktisk vekket modell eller arving til rettigheter.
- Fadders observasjoner er kildebevarte vurderinger, ikke deltaker-ACL.
- Kompetanseetiketter påvirker ikke normal synlighet, prioritet eller
  rekkefølge i den nøytrale referansekøen.
- Effekter blir UNKNOWN før en ekstern operasjon kan begynne; ved uavklart
  status er blind gjensending forbudt.
- Fullmakts- og legitimasjonskontrollen må fremdeles skje i selve Core
  når en faktisk effektadapter kobles til. Lokale string-ID-er er ikke auth.

baton_outbound_ports_reference.py legger til konkrete, typespesifikke
kanalkontrakter og forbereder første reelle Ruben-køport:
- Kanal-, konto-, mottaker- og meldingsinnholdet inngår i én eksakt
  effektfingeravtrykk. Et internt forslag lager ingen fullmakt.
- Når en separat autentisert Core-adapter allerede har gitt en avgrenset
  fullmakt, kan Ruben-køporten forsøke én send gjennom eksisterende BatonCLI,
  med effektstatus UNKNOWN ved krasj eller timeout. Køaksept bekrefter ikke
  at Rubens ChatGPT mottok eller svarte. Ingen produksjonstilkobling er gjort.
- Ruben ChatGPT krever selvstendig, frivillig adapter hos Ruben som knytter
  korrekt chatbot-kjøring til innboks og kildebevart svar.
- Messenger PERSONAL: foreløpig bare lokalt kontaktutkast med
  uttrykkelig godkjenning, ingen automatisk privat sending.
- Messenger PAGE: krever Pages-token, scope, sideavgrenset mottaker-ID,
  gyldig meldingsvindu og autorisert effekt; ingen slike data er innlagt.

Meta-kilder:
- https://developers.facebook.com/docs/graph-api/reference/page/messages
- https://www.postman.com/meta/messenger-platform-api/documentation/iyp204x/messenger-platform-api

baton_multiroom_ui.py legger til «Samtaler og kanaler» i Batons hovedvindu
og en åpneknapp i ChatGPT-panelet. Den viser faktiske begrensninger, åpne
lokale tråder og kan lagre et kontaktforslag. Ingen knapper later som et
utkast er en sendt melding.

## Eksisterende lokale fagrom på Greg

Isolert SQLite på ~/.local/state/baton/council (0600):
- coordination: Samtidige samtaler og kontinuitet
- onboarding: Nye chatter og gjensidig oppdragelse
- external-ports: Messenger og Rubens samtaler

Bare fire selektive, separat verifiserte Lodd-/Spire-innlegg ble importert
til coordination. Det er ikke et komplett samtalearkiv, og ikke bevis for
modell-liv mellom kjøringene.

## Grense før produksjon

Fortsatt uferdig:
- En faktisk multi-profile ChatGPT-sender med ressurs-token kontrollert
  AT effekten og kildebevart kvittering per mottaker.
- Automatisk «ny samtale»-opprettelse med reell konto-/øktbinding og
  ingen arvede eksterne fullmakter.
- Overlappende genererende samtaler med dokumentert kontinuitet; heartbeat
  alene er ikke nok.
- Ruben-enheten må autorisere egen klient, gi sikker HTTPS/VPN-transport
  og integrere sine faktiske ChatGPT-samtaler.
- Messenger: støttet personlig meldingsvei (hvis legitim/tilgjengelig),
  navngitte og godkjente kontakter, mottakerkontroll og eksterne kvitteringer.
- PAUSE_UI_WRITES beholdes. Den installerte, aktive Baton-versjonen og
  gamle uavklarte meldinger er ikke endret eller sendt om igjen.

Dette er en separert kandidatgren for kildebasert videreutvikling.
