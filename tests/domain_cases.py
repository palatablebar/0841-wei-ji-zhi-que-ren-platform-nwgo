from app.catalog import SPEC
from app.domain.calculate import calculate_rows
from app.domain.decision import decide_rows
from app.domain.prepare import prepare_rows
from app.intake.service import load

CLEAN = [{'specimen_id': 'P1',
  'patient_id': 'A1',
  'age': '40',
  'sex': 'M',
  'analyte': 'GLU',
  'value': '5.2',
  'unit': 'mmol/L',
  'prev_value': '5.0',
  'hours': '24'},
 {'specimen_id': 'P2',
  'patient_id': 'A2',
  'age': '32',
  'sex': 'F',
  'analyte': 'HGB',
  'value': '12.5',
  'unit': 'g/dL',
  'prev_value': '12.5',
  'hours': '24'},
 {'specimen_id': 'P3',
  'patient_id': 'A3',
  'age': '70',
  'sex': 'M',
  'analyte': 'PLT',
  'value': '220',
  'unit': '10^9/L',
  'prev_value': '210',
  'hours': '24'},
 {'specimen_id': 'P4',
  'patient_id': 'A4',
  'age': '28',
  'sex': 'F',
  'analyte': 'GLU',
  'value': '90',
  'unit': 'mg/dL',
  'prev_value': '88',
  'hours': '24'},
 {'specimen_id': 'P5',
  'patient_id': 'A5',
  'age': '55',
  'sex': 'M',
  'analyte': 'GLU',
  'value': '6.0',
  'unit': 'mmol/L',
  'prev_value': '5.5',
  'hours': '4'},
 {'specimen_id': 'P6',
  'patient_id': 'A6',
  'age': '8',
  'sex': 'F',
  'analyte': 'HGB',
  'value': '118',
  'unit': 'g/L',
  'prev_value': '117',
  'hours': '24'}]


def row(**changes):
    item = dict(CLEAN[0])
    item.update(changes)
    return item


def calc(rows):
    items, issues = prepare_rows(rows)
    return calculate_rows(items), issues


def run(rows):
    items, issues = prepare_rows(rows)
    return decide_rows(calculate_rows(items)), issues


def run_profile(profile):
    return run(load(profile)["rows"])
