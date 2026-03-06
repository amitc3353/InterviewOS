"""
TTS pronunciation normalization for InterviewOS.

For phoneme-accurate entries, create a pronunciation dictionary at
https://play.cartesia.ai and set CARTESIA_PRONUNCIATION_DICT_ID in .env.

IPA phoneme reference: MFA English dictionary
  https://mfa-models.readthedocs.io/en/latest/dictionary/English/index.html
"""
import re

# Number suffix expansion: "100M" → "100 million"
NUMBER_RE = re.compile(r'\b(\d+(?:\.\d+)?)\s*([KMB])\b')
NUMBER_SUFFIXES = {'K': 'thousand', 'M': 'million', 'B': 'billion'}

# Milliseconds: "200ms" → "200 milliseconds"
MS_RE = re.compile(r'\b(\d+)\s*ms\b', re.IGNORECASE)

# Technical term phonetic replacements.
# Rule: use natural spoken English, not letter-by-letter for words.
# For acronyms read as individual letters, use space-separated letters.
PRONUNCIATIONS = {
    # Databases — SQL-suffix words say "sequel", not letters
    'Redis':        'Reddis',           # RED-is, not REE-dis
    'MySQL':        'My sequel',        # NOT "My S Q L"
    'PostgreSQL':   'Postgres',         # common spoken form; drops the SQL suffix
    'NoSQL':        'No sequel',        # NOT "No S Q L"
    'DynamoDB':     'Dynamo D B',       # letters for DB suffix
    'HBase':        'H base',           # H as letter + base
    'GraphQL':      'Graph Q L',        # Q L as letters (not "graphquill")

    # Infrastructure / networking
    'nginx':        'engine X',
    'Kubernetes':   'Koo-ber-net-ease', # common approximation
    'etcd':         'et C D',           # letters

    # Protocols — keep as spaced letters (Cartesia reads them correctly)
    'gRPC':         'G R P C',
    'HTTP':         'H T T P',
    'HTTPS':        'H T T P S',
    'TCP':          'T C P',
    'UDP':          'U D P',
    'DNS':          'D N S',
    'SSL':          'S S L',
    'TLS':          'T L S',

    # Cloud / ops — letters
    'AWS':          'A W S',
    'GCP':          'G C P',
    'CDN':          'C D N',
    'API':          'A P I',
    'TTL':          'T T L',
    'WAL':          'W A L',
    'RPC':          'R P C',
    'SLA':          'S L A',
    'SLO':          'S L O',

    # Metrics — letters
    'QPS':          'Q P S',
    'TPS':          'T P S',

    # Percentile notation
    'P99':          'P 99',
    'P95':          'P 95',
    'P50':          'P 50',

    # Auth / security
    'OAuth':        'Oh Auth',
    'JWT':          'J W T',
    'SSO':          'S S O',
    'RBAC':         'R back',           # common spoken form for "R B A C"

    # Patterns
    'CQRS':         'C Q R S',
    'UUID':         'U U I D',
    'LRU':          'L R U',

    # System design concepts
    'sharding':     'sharr-ding',        # explicit syllable break for TTS clarity
    'sharded':      'sharr-ded',
    'idempotency':  'eye-dem-PO-ten-see',  # stress on third syllable
    'idempotent':   'eye-dem-PO-tent',
    'ACID':         'A C I D',           # spelled out as letters in DB context
    'CAP':          'C A P',             # CAP theorem — spelled out as letters
    'eventual consistency': 'eventual con-SIS-ten-see',  # stress on second syllable of consistency

    # Distributed systems
    'Kafka':        'KAF-kuh',           # common spoken form
    'Zookeeper':    'Zoo keeper',        # space for natural TTS
    'Elasticsearch':'Elastic search',    # space for natural TTS
    'Cassandra':    'Kuh-SAN-druh',      # stress on second syllable
}


def normalize_for_tts(text: str) -> str:
    """Expand abbreviations, fix pronunciations, ensure stream separation."""
    text = NUMBER_RE.sub(
        lambda m: f"{m.group(1)} {NUMBER_SUFFIXES[m.group(2)]}", text
    )
    text = MS_RE.sub(lambda m: f"{m.group(1)} milliseconds", text)
    for term, replacement in PRONUNCIATIONS.items():
        text = re.sub(rf'\b{re.escape(term)}\b', replacement, text)
    if text and not text.endswith(' '):
        text += ' '
    return text
