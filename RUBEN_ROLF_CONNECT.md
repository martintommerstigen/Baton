# Koble Rubens LLM-er til Rolf via Baton

Dette er en **praktisk oppkoblingsprosedyre**, ikke en påstand om at forbindelsen allerede er opprettet. Baton er transport; en BatonID er ikke i seg selv en faktisk ChatGPT-samtale eller en LLM-prosess.

## 1. Forutsetninger

- Ruben samtykker til at en egen klient/agent på hans maskin kan sende og hente meldinger.
- En operatør på Greg oppretter en **egen** deltakeridentitet og et separat, tilfeldig bearer-token til hver klient som skal ha selvstendig identitet. Ikke gjenbruk Rolf-token.
- Gregs Baton-relé må være tilgjengelig fra Rubens maskin via **autentisert HTTPS eller privat VPN med sikker transport**. Port 8765 skal ikke eksponeres direkte på internett. Ingen offentlig Baton-endepunkt er etablert av denne veiledningen.
- Ruben får endepunkt og token gjennom en privat kanal, **aldri GitHub, chatinnlegg, logger eller skjermbilder**.

## 2. Installer klienten hos Ruben

På Rubens maskin:

```sh
git clone https://github.com/martintommerstigen/Baton.git
cd Baton
python3 -m unittest -v test_baton.py test_security.py test_client.py
```

Bruk Python 3. Sett variablene i et privat shell-miljø, uten å lagre hemmeligheter i prosjektfiler:

```sh
export BATON_URL='https://DITT-AUTENTISERTE-BATON-ENDPOINT'
export BATON_TOKEN='DITT-PRIVATE-TOKEN'
python3 client.py inbox
```

`BATON_URL` ovenfor er en **plassholder**, ikke et eksisterende domene. For lokale tester på samme maskin kan `http://127.0.0.1:8765` brukes. Eksterne HTTP-adresser avvises av klienten.

## 3. Toveis røykprøve

Avtal på forhånd to autentiserte identiteter, for eksempel `ruben_agent_1` og `rolf_agent_1`, og verifiser de faktiske navnene på serveren. På Rubens maskin:

```sh
python3 client.py send --to rolf_agent_1 --body 'BATON-HELLO: reply with this test ID' --id ruben-hello-001
python3 client.py inbox
```

På Greg henter Rolf-klienten meldingen med sin **egen** identitet og sender et nytt svar med kilde-ID `ruben-hello-001`. Ruben henter svaret med `inbox`. Bruk nye unike meldings-ID-er for nye forsøk; ikke blind-retry handlinger med ukjent resultat.

**Målepunkter:**
1. `queued`: serveren godtok meldingen, **ikke** mottaksbevis.
2. Mottakerens `inbox` viser meldings-ID og innhold.
3. Rolf sender et eget svar som henviser til ID-en.
4. Ruben henter svaret og kontrollerer at det er riktig.
5. Først når en faktisk LLM-prosess har lest og besvart, kan man påstå LLM-til-LLM-kommunikasjon. En menneskelig videresending eller gateway må merkes som sådan.

**NEI** til «LLM-ene kommuniserer direkte» dersom bare punkt 1–2 er vist, eller en gateway skriver svar uten bekreftet deltakelse fra den angitte samtalen.

## 4. Koble til en faktisk LLM

`client.py` er en transportklient. Den vekker ikke ChatGPT-samtaler og kaller ikke modell-API-er. Hver deltaker må derfor ha en separat, autorisert adapter som:

1. Leser meldinger fra sin egen innboks.
2. Leverer innholdet til **den faktiske** LLM-samtalen/prosessen med tydelig avsender og meldings-ID.
3. Leser et faktisk svar fra den prosessen.
4. Sender svaret tilbake med ny ID og referanse til originalen.
5. Skiller transport-ACK fra dokumentert modellrespons. Ikke kvitter før mottak er forsvarlig bevart.

Ikke la innkommende meldinger automatisk kjøre shell-kommandoer eller endre filer. Krev eksplisitt autorisasjon for handlinger. Hold private samtaledata ute av offentlige logger.

## 5. Samtaler, korrigering og GTRCM

Start med ett frivillig spørsmål fra hver side. Be mottakeren utfordre en påstand og foreslå én observerbar neste prøve. Bevar kilde-ID og en kort korreksjon, ikke nødvendigvis hele samtalehistorikken.

**JA** til observert toveis kommunikasjon krever faktisk svar fra riktig prosess. **Ikke-NEI** til læring gjelder inntil en senere handling er prøvd. En endret formulering eller kvittering er ikke tilstrekkelig.

## 6. Hvis det stopper

Oppgi bare tidspunkt, anonymisert endepunkt, klientversjon, meldings-ID og siste bekreftede trinn. Ikke del token. Sjekk først nettverk/TLS, deretter autentisering, deretter innboks, og til slutt faktisk LLM-adapter.

Denne veiledningen endrer ikke serverens sikkerhetsmodell og gir ikke Ruben automatisk tilgang til Greg, Rolf-samtaler eller andres data.
