import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('contract', Path(__file__).resolve().parents[1]/'scripts/project-contract.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

class ContractTests(unittest.TestCase):
    def valid(self):
        return {'schema':1, 'repository':'owner/repo', 'default_branch':'main', 'scope':'Fixture', 'stack':'Python 3',
                'setup':['python3', '--version'], 'checks':[{'name':'tests', 'command':['python3', '-m', 'unittest']}],
                'policy':{'workers':4, 'attempt_minutes':20, 'weekly_reserve':3, 'short_reserve':25,
                          'retry_authority':'supervising-agent', 'automatic_publication':False, 'dispatch_enabled':False}}

    def test_complete_contract_is_structurally_valid(self):
        self.assertEqual(p.validate(self.valid()), [])

    def test_incomplete_contract_fails(self):
        self.assertTrue(p.validate({}))

    def test_cannot_silently_enable_dispatch_or_change_spend_policy(self):
        for key, value in [('dispatch_enabled', True), ('weekly_reserve', 0), ('workers', 2)]:
            data = self.valid(); data['policy'][key] = value
            self.assertTrue(p.validate(data))

    def test_shell_string_is_not_a_command_contract(self):
        data = self.valid(); data['setup'] = 'echo setup'
        self.assertTrue(p.validate(data))
