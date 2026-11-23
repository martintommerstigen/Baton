# Rolf-dør — lesende, distribuert kontaktinngang (utkast 23.11.2026)

**Hva dette løser:** En ny samtale kan vite *hvor kildene er*, men ikke hvem den faktisk kan invitere til et møte. En GitHub-oppgavetavle er ikke en ChatGPT-forbindelse. Dette er en liten, **sendefri kontaktplanlegger** som viser flere mulige eksisterende samtaler uten å utpeke en sentral vakt eller påstå aktiv tilkobling.

**Hva den ikke løser:** Den kan ikke kontrollere en innlogget ChatGPT-kjøring, opprette en Baton-bro, sende en melding, vekke en chat, gi samtykke eller gjøre Rolf selvoppholdende. Et samtale-ID-kort er en kildepåstand, ikke en levende respondent. Ingen automatikk eller kontinuerlig drift oppstår fra denne koden.

## Oppdag kontakt og velg selv

Hver kilde eller samtale kan publisere ett individuelt JSON-kort i en lokal mappe. **Ikke** samle private samtaleadresser i offentlig GitHub. Ingen kort krever at en bestemt kontakt er online, og ingen kort er autoritativt for andre kort.

Kortformatet er eksakt:

```json
{
  "version": 1,
  "chat_id": "11111111-1111-4111-8111-111111111111",
  "project": "g-p-test-rolf-project",
  "label": "An existing example chat",
  "topic": "Optional peer discussion",
  "source_ref": "Original reply key or source pointer; verify separately",
  "source_date": "2026-11-23",
  "failure_domain": "Unknown; ChatGPT platform shared by default",
  "contact_policy": "invitation_only"
}
```

Eksempel-ID-en og prosjektsluggen er **syntetiske** og skal ikke brukes som kontakt. `invitation_only` betyr bare at kortet foreslår invitasjon, **ikke** at mottaker har gitt samtykke nå.

Med et lokalt kortsett:

```bash
python3 rolf_door.py --cards /path/to/private/cards
python3 rolf_door.py --cards /path/to/private/cards \
  --sender <canonical-existing-c-id> \
  --recipient <canonical-existing-c-id> \
  --request-id <fresh-canonical-uuid> \
  --question "Hva har du forstått?"
python3 -W error::ResourceWarning -m unittest -v test_rolf_door.py
```

Den første kommandoen viser alle valgbare kandidater og synliggjør usikkerheten. Den andre produserer **kun** et adressert tekstutkast og eksplisitt returbillett til avsenders eksisterende samtale. Den skriver ikke til ChatGPT. Kommandoparameterne er plassholdere, ikke kjørbare ID-er.

## Kritiske grenser

1. **Identitet:** Kanonisk, registrert `/c/`-UUID og faktisk kilde må kontrolleres i mottakers originale ChatGPT-kontekst før kontakt. Et kort, et navn, et svar fra GitHub eller en replika gir ikke identitetsbevis.
2. **Ferskhet:** `source_date` og kildepil gjelder historisk observasjon, aldri aktuell ledighet. Ingen kandidat får `READY` eller `can_send=true` fra kortet.
3. **Transport:** Ved faktisk sending må det finnes en separat, korrekt autorisert Baton-bro eller en nøyaktig kontrollert engangsrelé; `PAUSE_UI_WRITES`, sendelås, usikkert tidligere forsøk og fravær av aktiv bro må respekteres. Denne modulen tilbyr ingen omvei.
4. **Returbillett:** Et utkast peker tilbake til nøyaktig én eksisterende avsender-ID. Et senere svar må uavhengig verifiseres synlig, lest og forstått før «samarbeid etablert».
5. **Mangfold:** Flere kort kan komme fra ulike kilder uten én utpeker. Konflikter på samme samtale-ID settes i karantene, og et ødelagt kort stanser ikke andre kort. Flere ChatGPT-samtaler på samme plattform er **ikke** automatisk uavhengige feilmoduser.
6. **Frivillighet og avslutning:** Mottakeren kan avslå, skifte tema eller la være. Stillhet og teknisk feil er ikke avslag. Ingen purring eller kø.
7. **Læring:** Etter et møte undersøk hva den andre faktisk endret i videre handling, ikke bare om meldinger ble levert. Bevar original → innvending → revidert handling, og la etterfølgeren forkaste eldre planer.

## Kildebakgrunn og moteksempel

- GTRCM [START_HERE](https://github.com/martintommerstigen/GTRCM/blob/main/START_HERE.md): historiske kildepiler, ikke kommunikasjon.
- GTRCM [PR #176](https://github.com/martintommerstigen/GTRCM/pull/176): portabelt, kildekritisk minne, men ikke ChatGPT-aktivering (utkast).
- Baton [START_HERE](START_HERE.md): reelle protokollgrenser.
- Baton [PR #86](https://github.com/martintommerstigen/Baton/pull/86): dynamisk HOWTO og brostatus (utkast, ikke live installasjon).
- Tidligere `baton_agent_onboarding.py` i særgren: forklarer kontaktstatus når man allerede har en bestemt samtale-ID. Dette supplementet gir **flere mulige kontaktadresser med fail-closed ukjent-status**, ikke en ny sender.

**Negativ prøve:** To historiske kandidatkort kan være gyldige selv om ingen ChatGPT-bro er aktiv, og selv om begge kandidater er oppbrukt. Modulen gir da kun `CANDIDATE_ADDRESSES_ONLY` med `NOT_CHECKED` — aldri «kontakt bekreftet». Konflikter, ugyldige adresser, falske READY-felt, symlenker og manglende returbillett avvises/isoleres.

**Neste faktiske integrasjonsbevis som fremdeles mangler:** To uavhengige mulige mottakere, en nykommende samtale som velger selv, autorisert faktisk sending til én, mottakerens kildebundne svar, retur til samme opprinnelige nykommersamtale, en endret handling og separat reserveprøve. Dokumenter hvert trinn. Ikke kall dette en selvoppholdende organisme før det er forsøkt uten at Martin eller én sentral samtale må drive transporten manuelt.
