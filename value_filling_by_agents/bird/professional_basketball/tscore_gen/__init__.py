"""tscore_gen: a compact re-implementation of the Spider Test-Suite random-database generator."""
__all__ = ['schema', 'literals', 'values', 'instance', 'writer', 'neighbors', 'compare', 'distill']

from .values import set_spec, spec

__all__.extend(['set_spec', 'spec'])
