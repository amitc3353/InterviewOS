"""Tests for TTS pronunciation normalization — technical terms, numbers, abbreviations."""

import pytest

from backend.interview.tts_pronunciations import (
    normalize_for_tts,
    PRONUNCIATIONS,
    NUMBER_RE,
    MS_RE,
)


# ---------------------------------------------------------------------------
# Tests — Technical term pronunciations (existing + new additions)
# ---------------------------------------------------------------------------

def test_mysql_pronunciation():
    """MySQL is spoken as 'My sequel', not spelled out."""
    result = normalize_for_tts("We should use MySQL for this.")
    assert "My sequel" in result
    assert "MySQL" not in result


def test_postgresql_pronunciation():
    """PostgreSQL is spoken as 'Postgres'."""
    result = normalize_for_tts("PostgreSQL is a good choice.")
    assert "Postgres" in result


def test_redis_pronunciation():
    """Redis is spoken as 'Reddis'."""
    result = normalize_for_tts("Use Redis for caching.")
    assert "Reddis" in result


def test_kubernetes_pronunciation():
    """Kubernetes is spoken as 'Koo-ber-net-ease'."""
    result = normalize_for_tts("Deploy on Kubernetes.")
    assert "Koo-ber-net-ease" in result


# ---------------------------------------------------------------------------
# Tests — Newly added system design terms
# ---------------------------------------------------------------------------

def test_sharding_pronunciation():
    """sharding is spoken as 'sharr-ding' for TTS clarity."""
    result = normalize_for_tts("We can use sharding for horizontal scaling.")
    assert "sharr-ding" in result


def test_sharded_pronunciation():
    """sharded is spoken as 'sharr-ded'."""
    result = normalize_for_tts("The database is sharded across regions.")
    assert "sharr-ded" in result


def test_idempotency_pronunciation():
    """idempotency is spoken with stress on third syllable."""
    result = normalize_for_tts("We need to ensure idempotency.")
    assert "eye-dem-PO-ten-see" in result


def test_idempotent_pronunciation():
    """idempotent is spoken as 'eye-dem-PO-tent'."""
    result = normalize_for_tts("The API should be idempotent.")
    assert "eye-dem-PO-tent" in result


def test_acid_pronunciation():
    """ACID is spelled out as 'A C I D'."""
    result = normalize_for_tts("We need ACID compliance.")
    assert "A C I D" in result


def test_cap_pronunciation():
    """CAP (theorem) is spelled out as 'C A P'."""
    result = normalize_for_tts("According to CAP theorem.")
    assert "C A P" in result


def test_eventual_consistency_pronunciation():
    """eventual consistency has stress on second syllable of consistency."""
    result = normalize_for_tts("We can accept eventual consistency here.")
    assert "eventual con-SIS-ten-see" in result


def test_cqrs_pronunciation():
    """CQRS is spelled out as 'C Q R S'."""
    result = normalize_for_tts("Implement a CQRS pattern.")
    assert "C Q R S" in result


# ---------------------------------------------------------------------------
# Tests — Distributed systems terms
# ---------------------------------------------------------------------------

def test_kafka_pronunciation():
    """Kafka is spoken as 'KAF-kuh'."""
    result = normalize_for_tts("Use Kafka for event streaming.")
    assert "KAF-kuh" in result


def test_zookeeper_pronunciation():
    """Zookeeper is spoken as 'Zoo keeper'."""
    result = normalize_for_tts("Zookeeper handles coordination.")
    assert "Zoo keeper" in result


def test_elasticsearch_pronunciation():
    """Elasticsearch is spoken as 'Elastic search'."""
    result = normalize_for_tts("Index data in Elasticsearch.")
    assert "Elastic search" in result


def test_cassandra_pronunciation():
    """Cassandra is spoken as 'Kuh-SAN-druh'."""
    result = normalize_for_tts("Store in Cassandra.")
    assert "Kuh-SAN-druh" in result


# ---------------------------------------------------------------------------
# Tests — Number and unit normalization
# ---------------------------------------------------------------------------

def test_number_suffix_million():
    """100M is expanded to '100 million'."""
    result = normalize_for_tts("Handle 100M requests per day.")
    assert "100 million" in result


def test_number_suffix_thousand():
    """10K is expanded to '10 thousand'."""
    result = normalize_for_tts("10K QPS target.")
    assert "10 thousand" in result


def test_number_suffix_billion():
    """5B is expanded to '5 billion'."""
    result = normalize_for_tts("5B records total.")
    assert "5 billion" in result


def test_milliseconds_expansion():
    """200ms is expanded to '200 milliseconds'."""
    result = normalize_for_tts("Latency under 200ms.")
    assert "200 milliseconds" in result


def test_decimal_number_suffix():
    """1.5M is expanded to '1.5 million'."""
    result = normalize_for_tts("1.5M daily active users.")
    assert "1.5 million" in result


# ---------------------------------------------------------------------------
# Tests — Protocol and cloud abbreviations
# ---------------------------------------------------------------------------

def test_grpc_pronunciation():
    """gRPC is spelled as 'G R P C'."""
    result = normalize_for_tts("Use gRPC for service communication.")
    assert "G R P C" in result


def test_api_pronunciation():
    """API is spelled as 'A P I'."""
    result = normalize_for_tts("Expose a REST API.")
    assert "A P I" in result


def test_aws_pronunciation():
    """AWS is spelled as 'A W S'."""
    result = normalize_for_tts("Deploy on AWS.")
    assert "A W S" in result


def test_cdn_pronunciation():
    """CDN is spelled as 'C D N'."""
    result = normalize_for_tts("Use a CDN for static assets.")
    assert "C D N" in result


# ---------------------------------------------------------------------------
# Tests — Edge cases
# ---------------------------------------------------------------------------

def test_trailing_space_added():
    """normalize_for_tts adds trailing space for stream separation."""
    result = normalize_for_tts("Hello")
    assert result.endswith(" ")


def test_empty_string():
    """Empty string returns empty string."""
    result = normalize_for_tts("")
    assert result == ""


def test_no_terms_to_replace():
    """Plain text without technical terms passes through unchanged (plus trailing space)."""
    result = normalize_for_tts("Just a plain sentence")
    assert result == "Just a plain sentence "


def test_multiple_terms_in_one_sentence():
    """Multiple technical terms in one sentence are all replaced."""
    result = normalize_for_tts("Use Redis and MySQL with sharding")
    assert "Reddis" in result
    assert "My sequel" in result
    assert "sharr-ding" in result


def test_pronunciations_dict_contains_required_terms():
    """PRONUNCIATIONS dict contains all required system design terms."""
    required_terms = [
        'sharding', 'sharded', 'idempotency', 'idempotent',
        'CQRS', 'ACID', 'CAP', 'eventual consistency',
    ]
    for term in required_terms:
        assert term in PRONUNCIATIONS, f"Missing pronunciation for '{term}'"
