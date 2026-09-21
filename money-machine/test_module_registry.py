import mm_module_registry as registry


def test_all_registered_modules_import_without_execution():
    result = registry.status()
    assert set(result['modules']) == set(registry.MODULES)
    assert all(module['available'] for module in result['modules'].values())


def test_registry_preserves_non_autonomous_safety_gates():
    safety = registry.status()['safety']
    assert safety == {
        'automatic_send': False,
        'automatic_approval': False,
        'automatic_pricing': False,
        'experimental_modules_scheduled': False,
    }
