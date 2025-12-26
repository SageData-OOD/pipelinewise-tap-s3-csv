"""
Module to guess csv columns' types and build Json schema.
"""
import csv
import io

from typing import Dict, List, Any
from messytables import CSVTableSet, headers_guess, headers_processor, offset_processor, type_guess
from messytables.types import DecimalType, IntegerType
from singer import get_logger

LOGGER = get_logger('tap_s3_csv')


def generate_schema(samples: List[Dict], table_spec: Dict) -> Dict:
    """
    Guess columns types from the given samples and build json schema
    :param samples: List of dictionaries containing samples data from csv file(s)
    :param table_spec: table/stream specs given in the tap definition
    :return: dictionary where the keys are the headers and values are the guessed types - compatible with json schema
    """
    schema = {}

    table_set = CSVTableSet(_csv2bytesio(samples))

    row_set = table_set.tables[0]

    offset, headers = headers_guess(row_set.sample)
    row_set.register_processor(headers_processor(headers))
    row_set.register_processor(offset_processor(offset + 1))

    types = type_guess(row_set.sample, strict=True)

    # Check if any sample values contain decimal points (even .00) for integer-detected fields
    # This handles cases where samples show whole numbers but actual data has decimal strings
    integer_fields_with_decimals = set()
    for sample in samples:
        for key, value in sample.items():
            normalized_key = key.replace(' ', '_')
            if normalized_key not in integer_fields_with_decimals:
                if isinstance(value, str) and '.' in value:
                    try:
                        float(value)
                        integer_fields_with_decimals.add(normalized_key)
                    except (ValueError, TypeError):
                        pass

    for header, header_type in zip(headers, types):

        # Replace spaces with underscores
        header = header.replace(' ', '_')

        date_overrides = set(table_spec.get('date_overrides', []))

        if header in date_overrides:
            schema[header] = {'type': ['null', 'string'], 'format': 'date-time'}
        else:
            if isinstance(header_type, IntegerType):
                # If we found decimal strings in samples, treat as number instead of integer
                if header in integer_fields_with_decimals:
                    schema[header] = {
                        'type': ['null', 'number']
                    }
                else:
                    schema[header] = {
                        'type': ['null', 'integer']
                    }
            elif isinstance(header_type, DecimalType):
                schema[header] = {
                    'type': ['null', 'number']
                }
            else:
                schema[header] = {
                    'type': ['null', 'string']
                }

    return schema


def _csv2bytesio(data: List[Dict]) -> io.BytesIO:
    """
    Converts a list of dictionaries to a csv BytesIO which is a csv file like object
    :param data: List of dictionaries to turn into csv like structure
    :return: BytesIO, a file like object in memory
    """
    with io.StringIO() as sio:

        header = set()

        for datum in data:
            header.update(list(datum.keys()))

        writer = csv.DictWriter(sio, fieldnames=header)

        writer.writeheader()
        writer.writerows(data)

        return io.BytesIO(sio.getvalue().strip('\r\n').encode('utf-8'))


def convert_value_to_schema_type(value: Any, schema_type: Dict) -> Any:
    """
    Convert a CSV string value to match the expected schema type.
    Note: Decimal strings for integer schemas are handled separately in convert_record_to_schema_types().
    
    :param value: The value to convert (typically a string from CSV)
    :param schema_type: The schema type definition (e.g., {'type': ['null', 'integer']})
    :return: The converted value matching the schema type
    """
    if value is None or value == '':
        return None
    
    types = schema_type.get('type', [])
    if not isinstance(types, list):
        types = [types]
    
    actual_types = [t for t in types if t != 'null']
    if not actual_types:
        return value
    
    target_type = actual_types[0]
    
    if target_type == 'integer':
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(float(value))
            except (ValueError, TypeError):
                return value
    
    elif target_type == 'number':
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return value
    
    return value


def convert_record_to_schema_types(record: Dict, schema: Dict) -> Dict:
    """
    Convert all values in a record to match their schema types.
    If a field is typed as integer but contains decimal strings, convert to float
    and update the schema type to number (to match destination table expectations).
    
    :param record: Dictionary of field name -> value
    :param schema: Full JSON schema with 'properties' containing field schemas (may be modified)
    :return: Record with converted values
    """
    if 'properties' not in schema:
        return record
    
    converted = {}
    properties = schema['properties']
    
    for key, value in record.items():
        if key in properties:
            field_schema = properties[key]
            
            # Check if schema says integer but value is a decimal string
            # Convert to float and update schema to number to match destination table
            types = field_schema.get('type', [])
            if not isinstance(types, list):
                types = [types]
            
            actual_types = [t for t in types if t != 'null']
            if actual_types and actual_types[0] == 'integer' and isinstance(value, str) and '.' in value:
                try:
                    converted[key] = float(value)
                    field_schema['type'] = ['null', 'number']
                    LOGGER.warning(
                        "Field '%s' was discovered as integer but contains decimal values (e.g., '%s'). "
                        "Updating schema type to 'number' to match destination table.",
                        key, value
                    )
                except (ValueError, TypeError):
                    converted[key] = convert_value_to_schema_type(value, field_schema)
            else:
                converted[key] = convert_value_to_schema_type(value, field_schema)
        else:
            # Keep fields not in schema as-is
            converted[key] = value
    
    return converted
