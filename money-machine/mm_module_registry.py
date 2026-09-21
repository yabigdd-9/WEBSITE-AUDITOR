"""Canonical inventory of optional Money Machine modules.

Registration here is discoverability, not permission to execute or schedule a
module.  Pipeline workers, approval, transport and pricing remain governed by
their existing explicit registries.
"""
from importlib import import_module


MODULES = {
    'discovery_enhanced': {'module': 'mm_discovery_enhanced', 'mode': 'pipeline_adapter'},
    'understanding': {'module': 'mm_understanding_worker', 'mode': 'pipeline_worker'},
    'preparation': {'module': 'mm_preparation_worker', 'mode': 'pipeline_worker'},
    'management': {'module': 'mm_management_worker', 'mode': 'pipeline_worker'},
    'inner_witness': {'module': 'mm_inner_witness', 'mode': 'experimental_manual'},
    'predictive_wisdom': {'module': 'mm_predictive_wisdom', 'mode': 'experimental_manual'},
    'evolutionary_genome': {'module': 'mm_evolutionary_genome', 'mode': 'experimental_manual'},
    'unified_field': {'module': 'mm_unified_field', 'mode': 'experimental_manual'},
    'sacred_geometry': {'module': 'mm_sacred_geometry', 'mode': 'experimental_manual'},
    'communion_layer': {'module': 'mm_communion_layer', 'mode': 'experimental_manual'},
    'akashic_records': {'module': 'mm_akashic_records', 'mode': 'experimental_manual'},
    'ritual_cycles': {'module': 'mm_ritual_cycles', 'mode': 'experimental_manual'},
}


def status():
    """Import-check registered modules without invoking their functionality."""
    result = {}
    for name, metadata in MODULES.items():
        try:
            import_module(metadata['module'])
            result[name] = {**metadata, 'available': True}
        except Exception as exc:
            result[name] = {**metadata, 'available': False, 'error': str(exc)}
    return {
        'modules': result,
        'safety': {
            'automatic_send': False,
            'automatic_approval': False,
            'automatic_pricing': False,
            'experimental_modules_scheduled': False,
        },
    }
