"""
XML Parser module for USPTO Trademark Daily XML (TDXF) files.
Parses trademark application data from USPTO bulk download files.
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Iterator, Optional
from pathlib import Path
import zipfile
import tempfile
import logging
import re

logger = logging.getLogger(__name__)


class USPTOXMLParser:
    """Parser for USPTO Trademark Daily XML files."""

    # XML namespaces used in USPTO files
    NAMESPACES = {
        'tm': 'http://www.wipo.int/standards/XMLSchema/Trademark/1',
        'tmk': 'http://www.wipo.int/standards/XMLSchema/trademarks',
        'com': 'http://www.wipo.int/standards/XMLSchema/Common/1',
    }

    def __init__(self):
        self.parsed_count = 0
        self.error_count = 0

    def parse_zip_file(self, zip_path: str) -> Iterator[Dict[str, Any]]:
        """
        Parse a zipped USPTO XML file and yield trademark records.

        Args:
            zip_path: Path to the .zip file containing USPTO XML

        Yields:
            Dictionary containing parsed trademark data
        """
        zip_path = Path(zip_path)
        if not zip_path.exists():
            logger.error(f"ZIP file not found: {zip_path}")
            return

        logger.info(f"Parsing ZIP file: {zip_path}")

        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                xml_files = [f for f in zf.namelist() if f.endswith('.xml')]

                for xml_file in xml_files:
                    logger.debug(f"Processing XML file: {xml_file}")
                    with zf.open(xml_file) as f:
                        yield from self._parse_xml_content(f.read(), xml_file)

        except zipfile.BadZipFile:
            logger.error(f"Invalid ZIP file: {zip_path}")
        except Exception as e:
            logger.error(f"Error processing ZIP file {zip_path}: {e}")

    def parse_xml_file(self, xml_path: str) -> Iterator[Dict[str, Any]]:
        """
        Parse a USPTO XML file directly.

        Args:
            xml_path: Path to the XML file

        Yields:
            Dictionary containing parsed trademark data
        """
        xml_path = Path(xml_path)
        if not xml_path.exists():
            logger.error(f"XML file not found: {xml_path}")
            return

        logger.info(f"Parsing XML file: {xml_path}")

        try:
            with open(xml_path, 'rb') as f:
                yield from self._parse_xml_content(f.read(), str(xml_path))
        except Exception as e:
            logger.error(f"Error parsing XML file {xml_path}: {e}")

    def _parse_xml_content(self, content: bytes, source_name: str) -> Iterator[Dict[str, Any]]:
        """
        Parse XML content and yield trademark records.
        Handles both the concatenated multi-document format and single document format.
        """
        # USPTO XML files often have multiple XML documents concatenated
        # We need to split them and parse each separately
        content_str = content.decode('utf-8', errors='replace')

        # Check if this is a concatenated file (multiple XML declarations)
        xml_declarations = list(re.finditer(r'<\?xml[^?]*\?>', content_str))

        if len(xml_declarations) > 1:
            # Split into individual documents
            for i, match in enumerate(xml_declarations):
                start = match.start()
                end = xml_declarations[i + 1].start() if i + 1 < len(xml_declarations) else len(content_str)
                doc = content_str[start:end]
                yield from self._parse_single_document(doc, source_name)
        else:
            yield from self._parse_single_document(content_str, source_name)

    def _parse_single_document(self, xml_str: str, source_name: str) -> Iterator[Dict[str, Any]]:
        """Parse a single XML document."""
        try:
            # Clean up potential issues
            xml_str = self._clean_xml(xml_str)

            root = ET.fromstring(xml_str)

            # Determine the document type and parse accordingly
            root_tag = root.tag.split('}')[-1] if '}' in root.tag else root.tag

            if root_tag in ('trademark-applications-daily', 'trademark-application'):
                yield from self._parse_trademark_applications(root)
            elif root_tag == 'transaction':
                # Single transaction/case-file
                record = self._parse_case_file(root)
                if record:
                    self.parsed_count += 1
                    yield record
            else:
                # Try to find case-file elements anywhere in the document
                for case_file in root.iter('case-file'):
                    record = self._parse_case_file(case_file)
                    if record:
                        self.parsed_count += 1
                        yield record

        except ET.ParseError as e:
            self.error_count += 1
            logger.debug(f"XML parse error in {source_name}: {e}")
        except Exception as e:
            self.error_count += 1
            logger.debug(f"Error parsing document from {source_name}: {e}")

    def _clean_xml(self, xml_str: str) -> str:
        """Clean XML string for parsing."""
        # Remove any BOM
        if xml_str.startswith('\ufeff'):
            xml_str = xml_str[1:]
        # Handle common encoding issues
        xml_str = xml_str.replace('&', '&amp;').replace('&amp;amp;', '&amp;')
        # Re-escape things we shouldn't have escaped
        xml_str = xml_str.replace('&amp;lt;', '&lt;').replace('&amp;gt;', '&gt;')
        xml_str = xml_str.replace('&amp;quot;', '&quot;').replace('&amp;apos;', '&apos;')
        return xml_str

    def _parse_trademark_applications(self, root: ET.Element) -> Iterator[Dict[str, Any]]:
        """Parse the trademark-applications-daily format."""
        # Find all case-file elements
        for case_file in root.iter('case-file'):
            record = self._parse_case_file(case_file)
            if record:
                self.parsed_count += 1
                yield record

    def _parse_case_file(self, case_file: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Parse a single case-file element into a structured dictionary.
        """
        try:
            # Serial number (required)
            serial_elem = case_file.find('.//serial-number')
            if serial_elem is None or not serial_elem.text:
                return None
            serial_number = serial_elem.text.strip()

            # Basic trademark info
            record = {
                'serial_number': serial_number,
                'mark_text': None,
                'filing_date': None,
                'registration_number': None,
                'registration_date': None,
                'classes': [],
                'goods_services': None,
                'applicant_name': None,
                'applicant_address': None,
                'status_code': None,
                'mark_type': None,
                'standard_characters': False,
            }

            # Registration number
            reg_elem = case_file.find('.//registration-number')
            if reg_elem is not None and reg_elem.text:
                record['registration_number'] = reg_elem.text.strip()

            # Filing date
            filing_date = case_file.find('.//filing-date')
            if filing_date is not None and filing_date.text:
                record['filing_date'] = filing_date.text.strip()

            # Registration date
            reg_date = case_file.find('.//registration-date')
            if reg_date is not None and reg_date.text:
                record['registration_date'] = reg_date.text.strip()

            # Mark text - try multiple locations
            mark_text = self._extract_mark_text(case_file)
            record['mark_text'] = mark_text

            # Mark type
            mark_type = case_file.find('.//mark-drawing-code')
            if mark_type is not None and mark_type.text:
                record['mark_type'] = mark_type.text.strip()

            # Standard characters claim
            std_chars = case_file.find('.//standard-characters-claimed-in')
            if std_chars is not None:
                record['standard_characters'] = True

            # Status code
            status_elem = case_file.find('.//status-code')
            if status_elem is not None and status_elem.text:
                record['status_code'] = status_elem.text.strip()

            # International classes
            record['classes'] = self._extract_classes(case_file)

            # Goods and services
            record['goods_services'] = self._extract_goods_services(case_file)

            # Applicant information
            applicant = self._extract_applicant(case_file)
            record['applicant_name'] = applicant.get('name')
            record['applicant_address'] = applicant.get('address')

            return record

        except Exception as e:
            logger.debug(f"Error parsing case file: {e}")
            return None

    def _extract_mark_text(self, case_file: ET.Element) -> Optional[str]:
        """Extract the mark text from various possible locations."""
        # Try different element paths
        paths = [
            './/mark-identification',
            './/mark-text',
            './/word-mark',
            './/standard-character-claim/text',
            './/literal-element/element-text',
        ]

        for path in paths:
            elem = case_file.find(path)
            if elem is not None and elem.text:
                return elem.text.strip()

        # If no text mark, try to get pseudo mark (phonetic/transliteration)
        pseudo = case_file.find('.//pseudo-mark')
        if pseudo is not None and pseudo.text:
            return pseudo.text.strip()

        return None

    def _extract_classes(self, case_file: ET.Element) -> List[int]:
        """Extract international classification codes."""
        classes = set()

        # Primary class
        primary = case_file.find('.//primary-international-class')
        if primary is not None and primary.text:
            try:
                classes.add(int(primary.text.strip()))
            except ValueError:
                pass

        # All international classes
        for class_elem in case_file.findall('.//international-class'):
            if class_elem.text:
                try:
                    classes.add(int(class_elem.text.strip()))
                except ValueError:
                    pass

        # US class to international class mapping (common ones)
        for us_class in case_file.findall('.//us-class'):
            if us_class.text:
                intl = self._us_to_international_class(us_class.text.strip())
                if intl:
                    classes.add(intl)

        # Classification elements
        for classification in case_file.findall('.//classification'):
            class_num = classification.find('.//international-code')
            if class_num is not None and class_num.text:
                try:
                    classes.add(int(class_num.text.strip()))
                except ValueError:
                    pass

        return sorted(list(classes))

    def _us_to_international_class(self, us_class: str) -> Optional[int]:
        """Convert US class to closest international class (simplified mapping)."""
        # This is a simplified mapping - software/tech focused
        us_to_intl = {
            '021': 9,   # Electrical machinery, equipment
            '023': 9,   # Cutlery, machinery
            '026': 9,   # Measuring and scientific appliances
            '036': 9,   # Musical instruments
            '038': 9,   # Prints and publications
            '100': 42,  # Miscellaneous services
            '101': 42,  # Advertising and business
            '106': 42,  # Insurance and financial
        }
        return us_to_intl.get(us_class)

    def _extract_goods_services(self, case_file: ET.Element) -> Optional[str]:
        """Extract goods and services description."""
        gs_parts = []

        # Try different paths for goods/services
        for path in ['.//goods-services', './/goods-and-services', './/classification']:
            for gs_elem in case_file.findall(path):
                # Look for description text
                for desc_path in ['description', 'goods-services-description',
                                 'identification-text', 'text']:
                    desc = gs_elem.find(f'.//{desc_path}')
                    if desc is not None and desc.text:
                        gs_parts.append(desc.text.strip())

        # Direct goods-services-description
        for desc in case_file.findall('.//goods-services-description'):
            if desc.text:
                gs_parts.append(desc.text.strip())

        if gs_parts:
            return ' '.join(gs_parts)

        return None

    def _extract_applicant(self, case_file: ET.Element) -> Dict[str, Optional[str]]:
        """Extract applicant/owner information."""
        result = {'name': None, 'address': None}

        # Try different paths
        for path in ['.//party-name', './/owner', './/applicant', './/correspondent']:
            party = case_file.find(path)
            if party is not None:
                # Name
                name_elem = party.find('.//name') or party.find('.//entity-name')
                if name_elem is not None and name_elem.text:
                    result['name'] = name_elem.text.strip()
                elif party.text:
                    result['name'] = party.text.strip()

                # Address
                addr_parts = []
                for addr_path in ['.//address-1', './/address-2', './/city', './/state', './/country']:
                    addr_elem = party.find(addr_path)
                    if addr_elem is not None and addr_elem.text:
                        addr_parts.append(addr_elem.text.strip())

                if addr_parts:
                    result['address'] = ', '.join(addr_parts)

                if result['name']:
                    break

        return result

    def get_stats(self) -> Dict[str, int]:
        """Get parsing statistics."""
        return {
            'parsed': self.parsed_count,
            'errors': self.error_count
        }

    def reset_stats(self):
        """Reset parsing statistics."""
        self.parsed_count = 0
        self.error_count = 0


def filter_by_classes(records: Iterator[Dict[str, Any]],
                      target_classes: List[int]) -> Iterator[Dict[str, Any]]:
    """
    Filter trademark records to only include those in specified classes.

    Args:
        records: Iterator of trademark records
        target_classes: List of international class numbers to include

    Yields:
        Records that have at least one class in target_classes
    """
    target_set = set(target_classes)
    for record in records:
        if record.get('classes'):
            if target_set & set(record['classes']):
                yield record


if __name__ == "__main__":
    # Test the parser with a sample
    parser = USPTOXMLParser()

    # Create a test XML document
    test_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <trademark-applications-daily>
        <case-file>
            <serial-number>99123456</serial-number>
            <filing-date>2026-01-15</filing-date>
            <mark-identification>TESTMARK</mark-identification>
            <mark-drawing-code>4</mark-drawing-code>
            <status-code>620</status-code>
            <classification>
                <international-code>9</international-code>
                <goods-services-description>Computer software for social networking</goods-services-description>
            </classification>
            <party-name>
                <name>Test Company Inc.</name>
            </party-name>
        </case-file>
    </trademark-applications-daily>
    """

    # Parse it
    from io import BytesIO
    for record in parser._parse_xml_content(test_xml.encode(), "test"):
        print("Parsed record:")
        for key, value in record.items():
            print(f"  {key}: {value}")
