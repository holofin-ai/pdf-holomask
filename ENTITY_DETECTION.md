# Entity Detection Configuration

This document explains how to customize the types of sensitive information that PDF Holomask detects and anonymizes.

## Overview

PDF Holomask uses AI (Mistral) to detect sensitive information in PDF documents. The types of entities to detect are configured in `entity_config.yaml`, making it easy to customize for your specific use case.

## Configuration File

The main configuration file is **`entity_config.yaml`** in the project root. This file defines:

1. **Entity Types**: What types of sensitive information to look for
2. **Descriptions**: Human-readable explanations of each entity type
3. **Examples**: Sample data to help the AI understand what to detect
4. **Enabled/Disabled**: Toggle entity detection on or off per type

## Entity Configuration Structure

Each entity in `entity_config.yaml` has the following structure:

```yaml
- type: "Entity Type Name"
  description: "Clear description of what this entity represents"
  example: "Sample data format"
  enabled: true  # or false to disable
```

### Example Entry

```yaml
- type: "Company Name"
  description: "Company and organization names"
  example: "Acme Corporation S.A."
  enabled: true
```

## Default Entity Types

The following entity types are included by default:

### Financial Identifiers
- **Registration/Company Registration Code**: Company registration numbers
- **VAT Number**: VAT identification numbers
- **IBAN**: International Bank Account Numbers
- **Bank Account Number**: Bank account numbers (non-IBAN)
- **Credit Card Number**: Credit card numbers

### Personal Identifiers
- **Person Name**: Individual person names
- **Email Address**: Email addresses
- **Phone Number**: Phone numbers (all formats)
- **Social Security Number**: Social security or national ID numbers

### Company Information
- **Company Name**: Company and organization names ✨ *Included!*
- **Client Name**: Client names (individual or company)

### Address Information
- **Address**: Physical addresses (street, city, postal code)

### Document Numbers
- **Invoice Number**: Invoice and receipt numbers (disabled by default)
- **Contract Number**: Contract reference numbers (disabled by default)

### Other
- **Other Sensitive Identifier**: Catch-all for unspecified sensitive data

## How to Customize

### Adding a New Entity Type

1. Open `entity_config.yaml`
2. Add a new entry under the `entities:` section:

```yaml
entities:
  # ... existing entities ...

  - type: "Tax Identification Number"
    description: "Tax IDs for businesses and individuals"
    example: "12-3456789"
    enabled: true
```

3. Save the file
4. Restart the application (if running)

The AI will automatically start detecting this new entity type!

### Disabling an Entity Type

To stop detecting a specific entity type:

1. Open `entity_config.yaml`
2. Find the entity you want to disable
3. Change `enabled: true` to `enabled: false`:

```yaml
- type: "Invoice Number"
  description: "Invoice and receipt numbers"
  example: "INV-2024-001234"
  enabled: false  # ← Changed to false
```

### Modifying Entity Descriptions

You can improve detection accuracy by providing better descriptions and examples:

```yaml
- type: "Company Name"
  description: "Full legal names of companies, including suffixes like Inc., Ltd., S.A., GmbH, etc."
  example: "TechVentures International S.A.R.L."
  enabled: true
```

Better descriptions help the AI understand exactly what to look for.

## Best Practices

### 1. Use Clear, Specific Descriptions

❌ **Bad**: "Company stuff"
✅ **Good**: "Company and organization names, including legal entity suffixes"

### 2. Provide Realistic Examples

Examples help the AI understand format and structure:

```yaml
example: "Acme Corp S.A."  # Good - shows company name with legal suffix
example: "Company"         # Bad - too generic
```

### 3. Start with Defaults Enabled

When adding new entity types, start with `enabled: true` and test thoroughly. You can always disable it later if it causes false positives.

### 4. Consider Regional Variations

If you work with international documents, include regional variations:

```yaml
- type: "Company Registration Number"
  description: "Company registration numbers (SIRET for France, CRN for UK, etc.)"
  example: "SIRET: 80529256400019 or CRN: 12345678"
  enabled: true
```

## Testing Your Configuration

After modifying the configuration:

1. Test with a sample document containing the entities you want to detect
2. Check the detection results in the UI
3. Adjust descriptions/examples if detection is inaccurate
4. Iterate until you get reliable results

## How It Works Under the Hood

1. **Loading**: When the application starts, `MistralAnalyzer` loads `entity_config.yaml`
2. **Prompt Generation**: Enabled entities are converted into a detection prompt for the AI
3. **AI Analysis**: Mistral AI scans the document for all enabled entity types
4. **Redaction**: Detected entities are replaced with synthetic data

The configuration is dynamic - you only need to edit the YAML file, no code changes required!

## Troubleshooting

### Entity Not Being Detected

1. Check that `enabled: true` in the config
2. Improve the description to be more specific
3. Add better examples that match your document's format
4. Verify the entity actually exists in your test document

### Too Many False Positives

1. Make the description more specific and restrictive
2. Consider disabling the entity type if it's not critical
3. Adjust the example to show the exact format you want

### Configuration Not Loading

1. Check the file is named `entity_config.yaml` (not `.yml`)
2. Check the file is in the project root directory
3. Look for YAML syntax errors (proper indentation, quotes, etc.)
4. Check application logs for error messages

## Contributing

When contributing new entity types or improvements:

1. Add the entity to `entity_config.yaml`
2. Test thoroughly with diverse documents
3. Document any regional or format-specific considerations
4. Submit a PR with your changes and test results

## Example: Detecting Industry-Specific Data

For a medical document processor:

```yaml
entities:
  - type: "Patient Name"
    description: "Full names of patients"
    example: "John Smith"
    enabled: true

  - type: "Medical Record Number"
    description: "Patient medical record identifiers"
    example: "MRN-123456"
    enabled: true

  - type: "Diagnosis Code"
    description: "ICD-10 diagnosis codes"
    example: "E11.9"
    enabled: true

  - type: "Prescription Number"
    description: "Prescription reference numbers"
    example: "RX-2024-00123"
    enabled: true
```

## Support

For questions or issues with entity detection:

1. Check the application logs for warnings/errors
2. Review this documentation
3. Open an issue on GitHub with:
   - Your configuration
   - Sample anonymized input
   - Expected vs actual behavior

---

**Made easy for contributors** 🎯 - Just edit YAML, no code changes needed!
