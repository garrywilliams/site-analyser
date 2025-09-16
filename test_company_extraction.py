#!/usr/bin/env python3
"""Test company name extraction from the database loader."""

from load_to_database import DatabaseLoader

# Test HMRC name cleaning
loader = DatabaseLoader()

test_names = [
    "! A Free Mobile MTDVAT! A Free Mobile MTDVAT is suitable for businesses or agents.Software type:Bridging software",
    "! Bridge It MTD! Bridge It MTD is suitable for businesses or agents.Software type:Bridging software",
    "#ABC VAT Bridge#ABC VAT Bridge is suitable for businesses or agents.Software type:Bridging software",
    "!Easy MTD VAT!Easy MTD VAT is suitable for businesses or agents.Software type:Record-keeping software",
    "Simple Company Name",
    "Good Company Ltd",
]

print("Testing HMRC company name cleaning:")
print("=" * 50)

for name in test_names:
    cleaned = loader._clean_hmrc_company_name(name)
    print(f"Original: {name[:80]}...")
    print(f"Cleaned:  {cleaned}")
    print("-" * 50)

# Test HTML extraction
test_html = """
<html>
<head>
    <title>Bridge IT MTD - VAT Software Solutions</title>
    <meta name="description" content="Professional VAT bridging software for Making Tax Digital compliance">
</head>
<body>
    <h1>Welcome to Bridge IT MTD</h1>
    <p>© 2023 Bridge IT Solutions Ltd. All rights reserved.</p>
</body>
</html>
"""

print("\nTesting HTML company name extraction:")
print("=" * 50)

html_info = loader.extract_company_info(test_html, "https://www.bridgeitmtd.co.uk")
print(f"Company Name: {html_info['company_name']}")
print(f"Summary: {html_info['summary']}")