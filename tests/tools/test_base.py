from oppie.tools.tickets import SEARCH_TICKETS_TOOL


def test_to_llm_schema_returns_expected_keys():
    schema = SEARCH_TICKETS_TOOL.to_llm_schema()

    assert set(schema.keys()) == {'name', 'description', 'schema'}


def test_to_llm_schema_preserves_values():
    schema = SEARCH_TICKETS_TOOL.to_llm_schema()

    assert schema['name'] == 'search_tickets'
    assert schema['description'] == SEARCH_TICKETS_TOOL.description
    assert schema['schema'] == SEARCH_TICKETS_TOOL.schema


def test_to_llm_schema_schema_is_json_schema_object():
    schema = SEARCH_TICKETS_TOOL.to_llm_schema()

    assert schema['schema']['type'] == 'object'
    assert 'properties' in schema['schema']
