import unittest

from tap_s3_csv.conversion import generate_schema, convert_value_to_schema_type, convert_record_to_schema_types


class TestConversion(unittest.TestCase):
    def test_generate_schema(self):
        samples = [
            dict(id='1', name='productA', added_at='2017/05/18 10:40:22', price='22.99', sold='true',
                 sold_at='2019-11-29'),
            dict(id='4', name='productB', added_at='2017/05/18 10:40:22', price='18', sold='false'),
            dict(id='6', name='productC', added_at='2017/05/18 10:40:22', price='14.6', sold='true',
                 sold_at='2019-12-11'),
        ]

        table_specs = {
            'date_overrides': ['added_at']
        }

        schema = generate_schema(samples, table_specs)

        self.assertDictEqual({
            'id': {
                'type': ['null', 'integer']
            },
            'name': {
                'type': ['null', 'string']
            },
            'added_at': {'type': ['null', 'string'], 'format':'date-time'},
            'price': {
                'type': ['null', 'number']
            },
            'sold': {
                'type': ['null', 'string']
            },
            'sold_at': {'type': ['null', 'string']}
        }, schema)

    def test_generate_schema_with_decimal_strings(self):
        """Test that schema discovery detects decimal strings and treats them as numbers"""
        samples = [
            dict(Bike_value='2799.00', Option='1'),
            dict(Bike_value='1500.00', Option='2'),
            dict(Bike_value='3000.00', Option='1'),
        ]

        table_specs = {}

        schema = generate_schema(samples, table_specs)

        # Bike_value should be detected as number (not integer) because it contains decimal strings
        self.assertEqual(schema['Bike_value']['type'], ['null', 'number'])
        # Option should be integer (whole numbers)
        self.assertEqual(schema['Option']['type'], ['null', 'integer'])

    def test_convert_value_to_schema_type_integer(self):
        """Test conversion of string values to integers"""
        schema_type = {'type': ['null', 'integer']}
        
        # Decimal string should convert to integer
        self.assertEqual(convert_value_to_schema_type('2799.00', schema_type), 2799)
        # Integer string should convert to integer
        self.assertEqual(convert_value_to_schema_type('1', schema_type), 1)
        # Already an integer should remain
        self.assertEqual(convert_value_to_schema_type(2799, schema_type), 2799)
        # None should remain None
        self.assertEqual(convert_value_to_schema_type(None, schema_type), None)
        # Empty string should become None
        self.assertEqual(convert_value_to_schema_type('', schema_type), None)

    def test_convert_value_to_schema_type_number(self):
        """Test conversion of string values to numbers"""
        schema_type = {'type': ['null', 'number']}
        
        # Decimal string should convert to float
        self.assertEqual(convert_value_to_schema_type('2799.00', schema_type), 2799.0)
        # Integer string should convert to float
        self.assertEqual(convert_value_to_schema_type('1', schema_type), 1.0)
        # Already a number should remain
        self.assertEqual(convert_value_to_schema_type(2799.5, schema_type), 2799.5)

    def test_convert_value_to_schema_type_string(self):
        """Test that string values remain strings"""
        schema_type = {'type': ['null', 'string']}
        
        # String should remain string
        self.assertEqual(convert_value_to_schema_type('test', schema_type), 'test')
        # Number string should remain string when schema expects string
        self.assertEqual(convert_value_to_schema_type('2799.00', schema_type), '2799.00')

    def test_convert_record_to_schema_types(self):
        """Test conversion of entire record"""
        record = {
            'Bike_value': '2799.00',
            'Option': '1',
            'Certificate_value': '2799.00',
            'Name': 'Test User'
        }
        schema = {
            'type': 'object',
            'properties': {
                'Bike_value': {'type': ['null', 'integer']},
                'Option': {'type': ['null', 'integer']},
                'Certificate_value': {'type': ['null', 'number']},
                'Name': {'type': ['null', 'string']}
            }
        }
        
        converted = convert_record_to_schema_types(record, schema)
        
        # Bike_value: decimal string with integer schema -> converts to float and updates schema to number
        self.assertEqual(converted['Bike_value'], 2799.0)
        self.assertEqual(schema['properties']['Bike_value']['type'], ['null', 'number'])
        # Option: whole number string with integer schema -> converts to integer
        self.assertEqual(converted['Option'], 1)
        # Certificate_value: already number schema -> converts to float
        self.assertEqual(converted['Certificate_value'], 2799.0)
        # Name: string schema -> remains string
        self.assertEqual(converted['Name'], 'Test User')

    def test_convert_record_to_schema_types_with_non_zero_decimals(self):
        """Test that non-zero decimal values (like 2799.99) are preserved as floats"""
        record = {
            'Price': '2799.99',
            'Discount': '1500.50'
        }
        schema = {
            'type': 'object',
            'properties': {
                'Price': {'type': ['null', 'integer']},
                'Discount': {'type': ['null', 'integer']}
            }
        }
        
        converted = convert_record_to_schema_types(record, schema)
        
        # Both should be converted to floats (preserving decimal precision)
        self.assertEqual(converted['Price'], 2799.99)
        self.assertEqual(converted['Discount'], 1500.50)
        # Schema should be updated to number
        self.assertEqual(schema['properties']['Price']['type'], ['null', 'number'])
        self.assertEqual(schema['properties']['Discount']['type'], ['null', 'number'])


if __name__ == '__main__':
    unittest.main()
