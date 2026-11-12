"""Versioned local HOWTO/FAQ knowledge for the Baton user interface.

Content may describe actions but CANNOT grant permissions, execute tools, send a
message, change Core, or lift PAUSE_UI_WRITES. Every update is a source-backed,
explicitly selected local UI action. Proposals never automatically go live.
"""
from contextlib import contextmanager
from pathlib import Path
import os
import re
import sqlite3

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,79}$")
KINDS = ("howto", "faq")
STATUSES = ("current", "challenged", "retired")
MAX_BODY = 16000


def _slug(value):
    if not isinstance(value, str) or not SLUG.fullmatch(value):
        raise ValueError("Ugyldig artikkel-ID (3–80 tegn, små bokstaver/tall/bindestrek)")
    return value


def _text(value, label, limit=MAX_BODY):
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= limit:
        raise ValueError(f"{label} må inneholde 2–{limit} tegn")
    return value.strip()


class HelpCatalog:
    def __init__(self, path=None):
        self.path = Path(path or (Path.home() / ".local/state/baton/help/catalog.sqlite3")).expanduser()

    @contextmanager
    def _db(self):
        c = sqlite3.connect(str(self.path), timeout=10)
        try:
            c.execute("PRAGMA busy_timeout=10000")
            c.execute("PRAGMA foreign_keys=ON")
            with c:
                yield c
        finally:
            c.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink() or self.path.is_symlink():
            raise ValueError("Symbolske lenker er ikke tillatt for hjelpedatabasen")
        with self._db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    slug TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK(kind IN ('howto','faq')),
                    current_revision INTEGER NOT NULL CHECK(current_revision>=1),
                    status TEXT NOT NULL DEFAULT 'current'
                       CHECK(status IN ('current','challenged','retired'))
                );
                CREATE TABLE IF NOT EXISTS article_versions (
                    slug TEXT NOT NULL REFERENCES articles(slug),
                    revision INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    PRIMARY KEY (slug, revision)
                );
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id INTEGER PRIMARY KEY,
                    slug TEXT NOT NULL REFERENCES articles(slug),
                    base_revision INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    source TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open'
                        CHECK(status IN ('open','applied','outdated','withdrawn')),
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS proposal_lookup
                    ON proposals(slug,status,proposal_id);
            """)
        os.chmod(self.path, 0o600)

    def add(self, slug, kind, title, body, source, reason="Opprettet lokalt"):
        slug = _slug(slug)
        if kind not in KINDS: raise ValueError("Ugyldig hjelpekategori")
        title = _text(title, "Tittel", 200)
        body = _text(body, "Innhold")
        source = _text(source, "Kilde", 1000)
        reason = _text(reason, "Begrunnelse", 2000)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("INSERT INTO articles(slug,kind,current_revision) VALUES(?,?,1)",
                      (slug,kind))
            c.execute("""INSERT INTO article_versions
                (slug,revision,title,body,source,reason) VALUES(?,1,?,?,?,?)""",
                (slug,title,body,source,reason))
        return self.get(slug)

    def get(self, slug):
        slug = _slug(slug)
        with self._db() as c:
            row=c.execute("""SELECT a.slug,a.kind,a.current_revision,a.status,
                  v.title,v.body,v.source,v.reason,v.created_at FROM articles a
                  JOIN article_versions v ON v.slug=a.slug
                   AND v.revision=a.current_revision
                  WHERE a.slug=?""",(slug,)).fetchone()
            if not row:return None
            history=c.execute("""SELECT revision,title,source,reason,created_at
                FROM article_versions WHERE slug=? ORDER BY revision DESC""",(slug,)).fetchall()
            pending=c.execute("""SELECT proposal_id,base_revision,title,body,source,reason,status
                FROM proposals WHERE slug=? ORDER BY proposal_id DESC""",(slug,)).fetchall()
            return {
                "slug":row[0], "kind":row[1], "revision":row[2], "status":row[3],
                "title":row[4], "body":row[5], "source":row[6], "reason":row[7],
                "modified":row[8],
                "history":[{"revision":h[0],"title":h[1],"source":h[2],
                            "reason":h[3],"modified":h[4]} for h in history],
                "proposals":[{"id":p[0],"base_revision":p[1],"title":p[2],
                              "body":p[3],"source":p[4],"reason":p[5],
                              "status":p[6]} for p in pending]
            }

    def list(self, kind=None, query=""):
        if kind is not None and kind not in KINDS: raise ValueError("Ugyldig kategori")
        if not isinstance(query,str) or len(query)>200: raise ValueError("For langt søk")
        # Parameterized LIKE; % and _ are treated literally, not wildcards.
        q=("%"+query.lower().replace("\\","\\\\").replace("%","\\%").replace("_","\\_")+"%")
        with self._db() as c:
            rows=c.execute("""SELECT a.slug FROM articles a JOIN article_versions v
                ON v.slug=a.slug AND v.revision=a.current_revision
                WHERE (? IS NULL OR a.kind=?)
                  AND (lower(v.title) LIKE ? ESCAPE '\\'
                    OR lower(v.body) LIKE ? ESCAPE '\\'
                    OR lower(a.slug) LIKE ? ESCAPE '\\')
                ORDER BY a.kind,v.title""",(kind,kind,q,q,q)).fetchall()
        return [self.get(r[0]) for r in rows]

    def propose(self, slug, base_revision, title, body, source, reason):
        slug=_slug(slug)
        if not isinstance(base_revision,int) or isinstance(base_revision,bool) or base_revision<1:
            raise ValueError("Ugyldig revisjonsnummer")
        title=_text(title,"Tittel",200)
        body=_text(body,"Innhold")
        source=_text(source,"Kilde",1000)
        reason=_text(reason,"Begrunnelse",2000)
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT current_revision FROM articles WHERE slug=?",(slug,)).fetchone()
            if row is None or row[0]!=base_revision:
                raise ValueError("Artikkelen er endret. Les gjeldende revisjon før nytt forslag.")
            cur=c.execute("""INSERT INTO proposals(slug,base_revision,title,body,source,reason)
                 VALUES(?,?,?,?,?,?)""",(slug,base_revision,title,body,source,reason))
            c.execute("UPDATE articles SET status='challenged' WHERE slug=? AND status='current'",(slug,))
        return cur.lastrowid

    def apply(self, proposal_id, expected_revision):
        if (not isinstance(proposal_id,int) or isinstance(proposal_id,bool) or proposal_id<1
                or not isinstance(expected_revision,int) or isinstance(expected_revision,bool)
                or expected_revision<1):
            raise ValueError("Ugyldig forslag eller revisjon")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            p=c.execute("""SELECT slug,base_revision,title,body,source,reason,status
                     FROM proposals WHERE proposal_id=?""",(proposal_id,)).fetchone()
            if not p or p[6]!="open":raise ValueError("Forslaget er ikke åpent")
            current=c.execute("SELECT current_revision FROM articles WHERE slug=?",(p[0],)).fetchone()
            if current is None or current[0]!=expected_revision or p[1]!=expected_revision:
                c.execute("UPDATE proposals SET status='outdated' WHERE proposal_id=?",
                          (proposal_id,))
                # On conflict, must inspect the new current version; no silent promotion.
                return {"applied":False,"reason":"stale"}
            new=expected_revision+1
            c.execute("""INSERT INTO article_versions(slug,revision,title,body,source,reason)
                    VALUES(?,?,?,?,?,?)""",(p[0],new,p[2],p[3],p[4],p[5]))
            c.execute("UPDATE articles SET current_revision=?,status='current' WHERE slug=?",
                      (new,p[0]))
            c.execute("UPDATE proposals SET status='applied' WHERE proposal_id=?",(proposal_id,))
            c.execute("UPDATE proposals SET status='outdated' WHERE slug=? AND status='open'",
                      (p[0],))
        return {"applied":True,"slug":p[0],"revision":new}

    def withdraw(self, proposal_id):
        if not isinstance(proposal_id,int) or proposal_id<1: raise ValueError("Ugyldig forslag")
        with self._db() as c:
            c.execute("BEGIN IMMEDIATE")
            row=c.execute("SELECT slug,status FROM proposals WHERE proposal_id=?",
                          (proposal_id,)).fetchone()
            if not row or row[1]!="open":return False
            c.execute("UPDATE proposals SET status='withdrawn' WHERE proposal_id=?",(proposal_id,))
            if not c.execute("SELECT 1 FROM proposals WHERE slug=? AND status='open'",(row[0],)).fetchone():
                c.execute("UPDATE articles SET status='current' WHERE slug=? AND status='challenged'",
                          (row[0],))
        return True

    def seed(self):
        """Insert initial, honest help text only if its slug is completely absent."""
        count=0
        for slug,kind,title,body in DEFAULT_ARTICLES:
            if self.get(slug) is not None:continue
            try:
                self.add(slug,kind,title,body,"Baton-kode og kildebevart arbeidsflyt, 2026-11-13",
                         "Starttekst for dynamisk HOWTO/FAQ. Kan foreslås korrigert.")
                count+=1
            except sqlite3.IntegrityError:
                pass  # Another local window may have seeded the exact slug.
        return count


DEFAULT_ARTICLES = (
    ("open-chat","howto","Åpne en eksisterende ChatGPT-samtale",
     "1. Kopier /c/-ID fra samtalen du faktisk vil bruke.\n"
     "2. Velg denne ID-en i Baton-panelet og åpne mottakeren.\n"
     "3. Kontroller at riktig eksisterende samtale vises før melding.\n"
     "En /c/-ID er en adresse, ikke identitetsbevis, skrivetillatelse eller et nytt modellminne."),
    ("send-and-verify","howto","Send og kontroller én melding",
     "1. Åpne riktig eksisterende samtale, kontroller mottaker og skriv meldingen.\n"
     "2. Kontroller om sending er tillatt; PAUSE_UI_WRITES må respekteres.\n"
     "3. Klikk Send én gang. Klikkforsøket er ikke bevis for levering.\n"
     "4. Undersøk korrekt melding og svar i den opprinnelige samtalen; gjeninnlasting kan kontrollere samme svar-ID.\n"
     "5. Ukjent levering: IKKE gjensend blindt. Bevar usikker status for undersøkelse."),
    ("peer-learning","howto","Samarbeid og læring mellom samtaler",
     "1. Undersøk tidligere arbeid og hva deltakeren allerede har vist i riktig kontekst.\n"
     "2. Inviter faglig motprøve fremfor å gi uønsket grunnopplæring.\n"
     "3. Skill gammel demonstrasjon fra nåværende verktøytilgang og kjørings-ID.\n"
     "4. Bevar hvem som foreslo, motsa og korrigerte hva. Stillhet er ikke avslag.\n"
     "5. Endringer i regelverk krever separat gyldig myndighet; en forumtråd gir ingen Core-tillatelse."),
    ("known-errors","howto","Undersøk kjente feil før en ny handling",
     "1. Søk etter relevant sviktmekanisme, ikke bare gammelt filnavn eller meldings-ID.\n"
     "2. Sammenlign kravet, betingelsene, effektgrensen og eventuelle moteksempler.\n"
     "3. Se om en nyere revisjon har erstattet den gamle generaliseringen.\n"
     "4. Bruk observasjonen som spørsmål/test, ikke automatisk dom eller blokkering.\n"
     "Den lokale læringsindeksen er foreløpig referanseprogramvare, ikke aktiv sikkerhetspolicy."),
    ("maintain-help","howto","Oppdater HOWTO eller FAQ dynamisk",
     "1. Velg artikkel og les gjeldende revisjon og historikk.\n"
     "2. Velg «Foreslå rettelse» med kilde og konkret begrunnelse.\n"
     "3. En innvending blir synlig, men endrer ikke automatisk rådet.\n"
     "4. Les det foreslåtte innholdet, og velg eksplisitt «Ta i bruk» hvis du vil aktivere det.\n"
     "5. Endringer bruker revisjonskontroll. Et foreldet forslag må vurderes på nytt.\n"
     "6. Nye FAQ-/HOWTO-artikler kan opprettes lokalt uten å endre gammel historikk."),
    ("disabled-send","faq","Hvorfor er Send deaktivert?",
     "Det kan skyldes tomt meldingsfelt, feil samtale, en tidligere send forsøkt med samme tekst, pågående sending eller PAUSE_UI_WRITES. Sjekk status i Baton. Å skru av en sikkerhetssperre er ikke en løsning på ukjent levering."),
    ("delivery-status","faq","Betyr Send-klikk at mottakeren har svart?",
     "Nei. Forsøkt, synlig levert, besvart og kontrollert etter gjeninnlasting er forskjellige hendelser. Et registrert svar-ID viser et observert svar, ikke at en modell har forstått eller har permanent tilgang."),
    ("always-active","faq","Holder Baton alltid minst én ChatGPT-kjøring aktiv?",
     "Ikke dokumentert i dagens produksjonssystem. Åpen samtale, ferskt svar, lokal prosess og faktisk kjørende modell er ulike ting. Et forslag om overlappende overlevering er testet i isolert referansekode, men må fortsatt integreres og verifiseres i reelle kjøringer."),
    ("same-error","faq","Hvorfor gjentar vi en feil som allerede er undersøkt?",
     "Gamle kilder kan mangle i den aktuelle kjøringen, og samme mekanisme kan oppstå med nye navn. Søk etter krav → sviktmekanisme → betingelser → moteksempel → revisjon. En lik handling er ikke automatisk samme feil; en gammel korrekt observasjon kan også bli brukt feil."),
    ("forum-status","faq","Er Baton-forumet ferdig og selvstyrende?",
     "Nei. Det finnes en isolert SQLite-modell for flere tråder og kildebevarte korreksjoner med tester. Det er ikke ennå en flerbruker nettjeneste, automatisk ChatGPT-transport eller en implementert plugin. Flere samtidige skrivere krever autentisert, ressursavgrenset adgang ved faktisk effekt."),
    ("scope-and-authority","faq","Hvem bestemmer en felles regel?",
     "Alle kan foreslå, argumentere og kritisere. Det gir ikke automatisk adgang til å utføre privilegerte handlinger, endre en annen deltakers gren eller overstyre Core. Konflikter skal begrenses til relevant handling; normal samtale trenger ikke stoppes."),
    ("faq-dynamics","faq","Hvordan blir denne hjelpen oppdatert?",
     "Denne visningen leser en lokal SQLite-katalog hver gang den oppdateres. Nye spørsmål og kildebelagte forslag kan registreres, men forslag blir aldri gjeldende uten en eksplisitt lokal godkjenning. Tidligere versjoner og uavklarte innvendinger forblir synlige."),
    ("start-new-chat","howto","Start her: ny ChatGPT-samtale i Baton",
     "1. Finn tilstanden i Baton-panelet før du lærer kommandoer: INBOUND_ONLY, BRIDGE_INACTIVE, BRIDGE_STARTING, PAUSED, READY eller UNCERTAIN.\n"
     "2. Velg og åpne din eksisterende /c/-samtale i Baton. Den vanlige ChatGPT-visningen alene gir IKKE Baton-verktøy.\n"
     "3. Bruk «Aktiver modellverktøy i åpen samtale» når det er tillatt. Baton sender da instruks og en fersk nonce til akkurat denne chatten.\n"
     "4. Svar med den eksakte testkommandoen Baton oppgir. Ikke finn på en nonce eller send et eksempel fra en annen kjøring.\n"
     "5. Kontroller Baton-verktøyresultatet. Først da kan utgående meldingsprotokoll brukes i samme autoriserte økt.\n"
     "6. Hvis PAUSE_UI_WRITES er aktiv: ikke forsøk å omgå den; les og diagnostiser. En kopiert HOWTO gir ingen sendetillatelse."),
    ("initiate-peer-chat","howto","Slik tar en SB selv initiativ til å chatte med en annen",
     "Forutsetning: Du har en aktiv Baton WORK SESSION med en fersk økt-nonce i DIN eksisterende chat, og skriverettigheten er ikke sperret.\n"
     "1. Finn nøyaktig /c/-ID til mottakeren fra en kilde du har kontrollert. Navn alene er ikke nok.\n"
     "2. Skriv EN linje BATON_CHAT_V1 <fersk-nonce> <ny-32-heks-request-id> <mottaker-chat-id> -- <én shell-sitert tekstmelding>. Dette er syntaksforklaring, IKKE en klar kommando.\n"
     "3. Mottakeren får en NY frivillig invitasjon. Vent på BATON_CHAT_RESULT_V1 og undersøk status, svar-ID og kilde.\n"
     "4. Er status usikker, skal du ikke gjenta samme kontakt blindt. Behold uavklart status.\n"
     "5. Er ingen gyldig nonce tilgjengelig? Da er din bro ikke bekreftet aktiv: bruk startguiden, ikke utgi en skrevet kommando for sendt melding.\n"
     "6. En annen SB kan kunne mer om Baton enn deg. Spør hva som faktisk har feilet før du gir opplæring."),
    ("outgoing-versus-receiving","faq","Hvorfor kan jeg svare Varde eller Spire, men ikke chatte selv?",
     "Fordi en mottatt invitasjon bare gir deg tekst i din eksisterende ChatGPT-samtale. Den aktiverer ikke automatisk en utgående modellbro. Den undersøkte Baton-visningen starter med auto_enable=False: aktiver verktøy i riktig visning, kontroller faktisk økt og sperrer før du sender. Et gammelt vellykket svar eller en DC-tilkobling beviser heller ikke utgående Baton-tilgang i denne kjøringen."),
    ("outgoing-states","faq","Hva betyr INBOUND_ONLY, BRIDGE_INACTIVE, PAUSED, READY og UNCERTAIN?",
     "INBOUND_ONLY: ingen bekreftet utgående kanal. BRIDGE_INACTIVE: åpen eksisterende chat, men ingen aktiv bro. BRIDGE_STARTING: oppstart startet, men ingen kontrollert verktøyrunde ennå. PAUSED: historisk sikkerhetssperre hindrer programmatisk send. READY: en lokal bro har behandlet et faktisk kall i akkurat denne økten, ikke garanti for modell-liv eller leverte meldinger. UNCERTAIN: uavklart effekt, ingen blind gjensending. Tilstanden skal bygge på observasjoner, ikke på navnet til chatten."),
    ("simultaneous-contact","faq","Hva hvis flere SB-er kontakter samme chat samtidig?",
     "Sjekk pågående kontakt, eksakt /c/-ID og seneste verifiserte svar-ID før en ny invitasjon. To gode hensikter kan ellers gi dobbel undervisning eller duplikatsending. Skriverett skal fordeles per faktisk vindu/profil, ikke gjennom en global samtalesperre. Dette er ennå ikke fullintegrert i produksjons-Baton."),
    ("stale-bridge-receipt","faq","Kan et gammelt testresultat gjøre en ny modellbro READY?",
     "NEI. En forsinket kvittering fra bro A må aldri markere bro B som klar, heller ikke i samme /c/-chat. Testresultatet må bindes til akkurat den kjøringen som startet det, samtale-ID, fersk nonce og brogenerasjon. En lokal test viser ikke at en annen ChatGPT-samtale kan motta meldinger. Basert på Søms negative moteksempel, 2026-11-13; integrasjon i aktiv sender er ennå ikke produksjonstestet."),
    ("rendered-markdown","faq","Hvorfor fant ikke Baton et svar som faktisk finnes i chatten?",
     "Visningen kan fjerne Markdown-formatering fra en sendt melding, for eksempel backticks rundt kode. Batons observer må kontrollere eksakt samtale og unik forespørsels-ID, samt samme tilgrensende assistent-ID etter gjeninnlasting; den skal ikke bare søke etter løse delstrenger. Usikker leveringsstatus er IKKE tillatelse til gjensending. Et konkret tilfelle ble motprøvd med Søm 2026-11-13."),
);
