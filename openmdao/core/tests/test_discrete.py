""" Unit tests for discrete variables."""

import sys
import unittest
import copy

from six import assertRaisesRegex, StringIO, assertRegex

import numpy as np

from openmdao.core.group import get_relevant_vars
from openmdao.core.driver import Driver
from openmdao.api import Problem, IndepVarComp, NonlinearBlockGS, ScipyOptimizeDriver, \
    ExecComp, Group, NewtonSolver, ImplicitComponent, ScipyKrylov, ExplicitComponent, \
    ImplicitComponent, ParallelGroup, BroydenSolver
from openmdao.utils.assert_utils import assert_rel_error
from openmdao.test_suite.components.paraboloid import Paraboloid
from openmdao.test_suite.components.sellar import StateConnection, \
     SellarDis1withDerivatives, SellarDis2withDerivatives
from openmdao.devtools.problem_viewer.problem_viewer import _get_viewer_data


class ModCompEx(ExplicitComponent):
    def __init__(self, modval, **kwargs):
        super(ModCompEx, self).__init__(**kwargs)
        self.modval = modval

    def setup(self):
        self.add_discrete_input('x', val=10)
        self.add_discrete_output('y', val=0)

    def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):
        discrete_outputs['y'] = discrete_inputs['x'] % self.modval


class ModCompIm(ImplicitComponent):
    def __init__(self, modval, **kwargs):
        super(ModCompIm, self).__init__(**kwargs)
        self.modval = modval

    def setup(self):
        self.add_discrete_input('x', val=10)
        self.add_discrete_output('y', val=0)

    def apply_nonlinear(self, inputs, outputs, residuals, discrete_inputs, discrete_outputs):
        discrete_outputs['y'] = discrete_inputs['x'] % self.modval

    def solve_nonlinear(self, inputs, outputs, discrete_inputs, discrete_outputs):
        discrete_outputs['y'] = discrete_inputs['x'] % self.modval


class CompDiscWDerivs(ExplicitComponent):
    def setup(self):
        self.add_discrete_input('N', 2)
        self.add_discrete_output('Nout', 2)
        self.add_input('x')
        self.add_output('y')
        self.declare_partials('*', '*')

    def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):
        discrete_outputs['Nout'] = discrete_inputs['N'] * 2
        outputs['y'] = inputs['x'] * 3.

    def compute_partials(self, inputs, partials, discrete_inputs):
        partials['y', 'x'] = 3.


class CompDiscWDerivsImplicit(StateConnection):
    def setup(self):
        super(CompDiscWDerivsImplicit, self).setup()
        self.add_discrete_input('N', 2)
        self.add_discrete_output('Nout', 2)

    def apply_nonlinear(self, inputs, outputs, residuals, discrete_inputs, discrete_outputs):
        super(CompDiscWDerivsImplicit, self).apply_nonlinear(inputs, outputs, residuals)
        discrete_outputs['Nout'] = discrete_inputs['N'] * 2

    def solve_nonlinear(self, inputs, outputs, discrete_inputs, discrete_outputs):
        super(CompDiscWDerivsImplicit, self).solve_nonlinear(inputs, outputs)
        discrete_outputs['Nout'] = discrete_inputs['N'] * 2

    def linearize(self, inputs, outputs, J, discrets_inputs, discrete_outputs):
        super(CompDiscWDerivsImplicit, self).linearize(inputs, outputs, J)


class MixedCompDiscIn(ExplicitComponent):
    def __init__(self, mult, **kwargs):
        super(MixedCompDiscIn, self).__init__(**kwargs)
        self.mult = mult

    def setup(self):
        self.add_discrete_input('x', val=1)
        self.add_output('y')

    def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):
        outputs['y'] = discrete_inputs['x'] * self.mult


class MixedCompDiscOut(ExplicitComponent):
    def __init__(self, mult, **kwargs):
        super(MixedCompDiscOut, self).__init__(**kwargs)
        self.mult = mult

    def setup(self):
        self.add_input('x')
        self.add_discrete_output('y', val=1)

    def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):
        discrete_outputs['y'] = inputs['x'] * self.mult


class InternalDiscreteGroup(Group):
    # this group has an internal discrete connection with continuous external vars,
    # so it can be spliced into an existing continuous model to test for discrete
    # var error checking.
    def setup(self):
        self.add_subsystem('C1', MixedCompDiscOut(1), promotes_inputs=['x'])
        self.add_subsystem('C2', MixedCompDiscIn(1), promotes_outputs=['y'])
        self.connect('C1.y', 'C2.x')


class DiscreteDriver(Driver):

    def __init__(self):
        super(DiscreteDriver, self).__init__()
        self.supports.declare('integer_design_vars', types=bool, default=True)

    def run(self):
        self.get_design_var_values()


class _DiscreteVal(object):
    """Generic discrete value to test passing of objects."""
    def __init__(self, val):
        self._val = val

    def getval(self):
        return self._val

    def setval(self, val):
        if isinstance(val, _DiscreteVal):
            val = val.getval()
        self._val = val

    def __iadd__(self, val):
        if isinstance(val, _DiscreteVal):
            val = val.getval()
        self._val += val
        return self

    def __imul__(self, val):
        if isinstance(val, _DiscreteVal):
            val = val.getval()
        self._val *= val
        return self


class PathCompEx(ExplicitComponent):

    def setup(self):
        self.add_discrete_input('x', val=self.pathname)
        self.add_discrete_output('y', val=self.pathname + '/')

    def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):
        discrete_outputs['y'] = discrete_inputs['x'] + self.pathname + '/'


class ObjAdderCompEx(ExplicitComponent):
    def __init__(self, val, **kwargs):
        super(ObjAdderCompEx, self).__init__(**kwargs)
        self.val = val

    def setup(self):
        self.add_discrete_input('x', val=self.val)
        self.add_discrete_output('y', val=copy.deepcopy(self.val))

    def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):
        discrete_outputs['y'].setval(discrete_inputs['x'].getval() + self.val.getval())


class DiscreteTestCase(unittest.TestCase):

    def test_simple_run_once(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_discrete_output('x', 11)
        model.add_subsystem('comp', ModCompEx(3))

        model.connect('indep.x', 'comp.x')

        prob.setup()
        prob.run_model()

        assert_rel_error(self, prob['comp.y'], 2)

    def test_simple_run_once_promoted(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp(), promotes=['*'])
        indep.add_discrete_output('x', 11)
        model.add_subsystem('comp', ModCompEx(3), promotes=['*'])

        prob.setup()
        prob.run_model()

        assert_rel_error(self, prob['y'], 2)

    def test_simple_run_once_implicit(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_discrete_output('x', 11)
        model.add_subsystem('comp', ModCompIm(3))

        model.connect('indep.x', 'comp.x')

        prob.setup()
        prob.run_model()

        assert_rel_error(self, prob['comp.y'], 2)

    def test_list_inputs_outputs(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_discrete_output('x', 11)

        model.add_subsystem('expl', ModCompEx(3))
        model.add_subsystem('impl', ModCompIm(3))

        model.connect('indep.x', ['expl.x', 'impl.x'])

        prob.setup()
        prob.run_model()

        # logging inputs
        # out_stream - not hierarchical - extras - no print_arrays
        stream = StringIO()
        prob.model.list_inputs(values=True,
                               units=True,
                               hierarchical=False,
                               print_arrays=False,
                               out_stream=stream)
        text = stream.getvalue()

        print(text)

        self.assertEqual(1, text.count("2 Input(s) in 'model'"))

        # make sure they are in the correct order
        self.assertTrue(text.find("sub1.sub2.g1.d1.z") <
                        text.find('sub1.sub2.g1.d1.x') <
                        text.find('sub1.sub2.g1.d1.y2') <
                        text.find('sub1.sub2.g1.d2.z') <
                        text.find('sub1.sub2.g1.d2.y1') <
                        text.find('g2.d1.z') <
                        text.find('g2.d1.x') <
                        text.find('g2.d1.y2') <
                        text.find('g2.d2.z') <
                        text.find('g2.d2.y1'))
        num_non_empty_lines = sum([1 for s in text.splitlines() if s.strip()])
        self.assertEqual(14, num_non_empty_lines)

        # out_stream - hierarchical - extras - no print_arrays
        stream = cStringIO()
        prob.model.list_inputs(values=True,
                               units=True,
                               hierarchical=True,
                               print_arrays=False,
                               out_stream=stream)
        text = stream.getvalue()

        print(text)

        self.assertEqual(1, text.count("10 Input(s) in 'model'"))
        num_non_empty_lines = sum([1 for s in text.splitlines() if s.strip()])
        self.assertEqual(23, num_non_empty_lines)
        self.assertEqual(1, text.count('top'))
        self.assertEqual(1, text.count('  sub1'))
        self.assertEqual(1, text.count('    sub2'))
        self.assertEqual(1, text.count('      g1'))
        self.assertEqual(1, text.count('        d1'))
        self.assertEqual(2, text.count('          z'))

        # logging outputs
        # out_stream - not hierarchical - extras - no print_arrays
        stream = cStringIO()
        prob.model.list_outputs(values=True,
                                units=True,
                                shape=True,
                                bounds=True,
                                residuals=True,
                                scaling=True,
                                hierarchical=False,
                                print_arrays=False,
                                out_stream=stream)
        text = stream.getvalue()

        print(text)

        self.assertEqual(text.count('5 Explicit Output'), 1)

        # make sure they are in the correct order
        self.assertTrue(text.find("pz.z") < text.find('sub1.sub2.g1.d1.y1') <
                        text.find('sub1.sub2.g1.d2.y2') <
                        text.find('g2.d1.y1') < text.find('g2.d2.y2'))
        num_non_empty_lines = sum([1 for s in text.splitlines() if s.strip()])
        self.assertEqual(11, num_non_empty_lines)

        # Hierarchical
        stream = cStringIO()
        prob.model.list_outputs(values=True,
                                units=True,
                                shape=True,
                                bounds=True,
                                residuals=True,
                                scaling=True,
                                hierarchical=True,
                                print_arrays=False,
                                out_stream=stream)
        text = stream.getvalue()

        print(text)

        self.assertEqual(text.count('top'), 1)
        self.assertEqual(text.count('          y1'), 1)
        self.assertEqual(text.count('  g2'), 1)
        num_non_empty_lines = sum([1 for s in text.splitlines() if s.strip()])
        self.assertEqual(num_non_empty_lines, 21)

    def test_float_to_discrete_error(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_output('x', 1.0)
        model.add_subsystem('comp', ModCompEx(3))

        model.connect('indep.x', 'comp.x')

        with self.assertRaises(Exception) as ctx:
            prob.setup()
        self.assertEqual(str(ctx.exception),
                         "Can't connect discrete output 'indep.x' to continuous input 'comp.x'.")

    def test_discrete_to_float_error(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_discrete_output('x', 1)
        model.add_subsystem('comp', ExecComp("y=2.0*x"))

        model.connect('indep.x', 'comp.x')

        with self.assertRaises(Exception) as ctx:
            prob.setup()
        self.assertEqual(str(ctx.exception),
                         "Can't connect discrete output 'indep.x' to continuous input 'comp.x'.")

    def test_discrete_mismatch_error(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_discrete_output('x', val='foo')
        model.add_subsystem('comp', ModCompEx(3))

        model.connect('indep.x', 'comp.x')

        with self.assertRaises(Exception) as ctx:
            prob.setup()
        self.assertEqual(str(ctx.exception),
                         "Type 'str' of output 'indep.x' is incompatible with type 'int' of input 'comp.x'.")

    def test_driver_discrete_enforce_int(self):
        # Drivers require discrete vars to be int or ndarrays of int.
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_discrete_output('x', 11)
        model.add_subsystem('comp', ModCompIm(3))

        model.connect('indep.x', 'comp.x')

        model.add_design_var('indep.x', 11)
        prob.driver = DiscreteDriver()
        prob.setup()

        # Insert a non integer
        prob['indep.x'] = 3.7

        with self.assertRaises(Exception) as ctx:
            prob.run_driver()

        msg = "Only integer scalars or ndarrays are supported as values for " + \
              "discrete variables when used as a design variable. "
        msg += "A value of type 'float' was specified."

        self.assertEqual(str(ctx.exception), msg)

        # Insert a float ndarray
        prob['indep.x'] = np.array([3.0])

        with self.assertRaises(Exception) as ctx:
            prob.run_driver()

        msg = "Only integer scalars or ndarrays are supported as values for " + \
              "discrete variables when used as a design variable. "
        msg += "An array of type 'float64' was specified."

        self.assertEqual(str(ctx.exception), msg)

        # Make sure these work.

        prob['indep.x'] = np.array([3.0], dtype=np.int64)
        prob.run_driver()

        prob['indep.x'] = 5
        prob.run_driver()

    def test_discrete_deriv_explicit(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_output('x', 1.0)

        comp = model.add_subsystem('comp', CompDiscWDerivs())
        model.connect('indep.x', 'comp.x')

        model.add_design_var('indep.x')
        model.add_objective('comp.y')

        prob.setup()
        prob.run_model()

        J = prob.compute_totals(return_format='array')

        np.testing.assert_almost_equal(J, np.array([[3.]]))

    def test_discrete_deriv_implicit(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp())
        indep.add_output('x', 1.0, ref=10.)
        indep.add_discrete_output('N', 1)

        comp = model.add_subsystem('comp', CompDiscWDerivsImplicit())
        sink = model.add_subsystem('sink', MixedCompDiscIn(1.0))
        model.connect('indep.x', 'comp.y2_actual')
        model.connect('indep.N', 'comp.N')
        model.connect('comp.Nout', 'sink.x')

        model.add_design_var('indep.x')
        model.add_objective('comp.y2_command')

        prob.setup()
        prob.run_model()

        J = prob.compute_totals(return_format='array')

        np.testing.assert_almost_equal(J, np.array([[-1]]))

    def test_deriv_err(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp(), promotes_outputs=['x'])
        indep.add_output('x', 1.0)

        G = model.add_subsystem('G', Group(), promotes_inputs=['x'])

        G1 = G.add_subsystem('G1', InternalDiscreteGroup(), promotes_inputs=['x'], promotes_outputs=['y'])

        G2 = G.add_subsystem('G2', Group(), promotes_inputs=['x'])
        G2.add_subsystem('C2_1', ExecComp('y=3*x'), promotes_inputs=['x'])
        G2.add_subsystem('C2_2', ExecComp('y=4*x'), promotes_outputs=['y'])
        G2.connect('C2_1.y', 'C2_2.x')

        model.add_subsystem('C3', ExecComp('y=3+x'))
        model.add_subsystem('C4', ExecComp('y=4+x'))

        model.connect('G.y', 'C3.x')
        model.connect('G.G2.y', 'C4.x')

        prob.model.add_design_var('x')
        prob.model.add_objective('C3.y')
        prob.model.add_constraint('C4.y')

        prob.setup()
        prob.run_model()

        self.assertEqual(prob['C3.y'], 4.0)
        self.assertEqual(prob['C4.y'], 16.0)

        with self.assertRaises(Exception) as ctx:
            J = prob.compute_totals()
        self.assertEqual(str(ctx.exception),
                         "Total derivative with respect to 'indep.x' depends upon discrete output variables ['G.G1.C1.y'].")


class SolverDiscreteTestCase(unittest.TestCase):
    def _setup_model(self, solver_class):
        prob = Problem()
        model = prob.model

        model.add_subsystem('px', IndepVarComp('x', 1.0), promotes=['x'])
        model.add_subsystem('pz', IndepVarComp('z', np.array([5.0, 2.0])), promotes=['z'])

        proms = ['x', 'z', 'y1', 'state_eq.y2_actual', 'state_eq.y2_command', 'd1.y2', 'd2.y2']
        sub = model.add_subsystem('sub', Group(), promotes=proms)

        subgrp = sub.add_subsystem('state_eq_group', Group(),
                                   promotes=['state_eq.y2_actual', 'state_eq.y2_command'])
        subgrp.add_subsystem('state_eq', StateConnection())

        sub.add_subsystem('d1', SellarDis1withDerivatives(), promotes=['x', 'z', 'y1'])
        sub.add_subsystem('d2', SellarDis2withDerivatives(), promotes=['z', 'y1'])

        model.connect('state_eq.y2_command', 'd1.y2')
        model.connect('d2.y2', 'state_eq.y2_actual')

        model.add_subsystem('obj_cmp', ExecComp('obj = x**2 + z[1] + y1 + exp(-y2)',
                                               z=np.array([0.0, 0.0]), x=0.0, y1=0.0, y2=0.0),
                           promotes=['x', 'z', 'y1', 'obj'])
        model.connect('d2.y2', 'obj_cmp.y2')

        model.add_subsystem('con_cmp1', ExecComp('con1 = 3.16 - y1'), promotes=['con1', 'y1'])
        model.add_subsystem('con_cmp2', ExecComp('con2 = y2 - 24.0'), promotes=['con2'])

        # splice a group containing discrete vars into the model
        model.add_subsystem('discrete_g', InternalDiscreteGroup())
        model.connect('d2.y2', 'discrete_g.x')
        model.connect('discrete_g.y', 'con_cmp2.y2')

        model.nonlinear_solver = solver_class()

        prob.set_solver_print(level=0)
        prob.setup(check=False)

        return prob

    def test_discrete_err_newton(self):
        prob = self._setup_model(NewtonSolver)

        with self.assertRaises(Exception) as ctx:
            prob.run_model()

        self.assertEqual(str(ctx.exception),
                         "System '' has a NewtonSolver solver and contains discrete outputs ['discrete_g.C1.y'].")

    def test_discrete_err_broyden(self):
        prob = self._setup_model(BroydenSolver)

        with self.assertRaises(Exception) as ctx:
            prob.run_model()

        self.assertEqual(str(ctx.exception),
                         "System '' has a BroydenSolver solver and contains discrete outputs ['discrete_g.C1.y'].")


class DiscretePromTestCase(unittest.TestCase):
    def test_str_pass(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp(), promotes_outputs=['x'])
        indep.add_discrete_output('x', 'indep/')

        G = model.add_subsystem('G', ParallelGroup(), promotes_inputs=['x'])

        G1 = G.add_subsystem('G1', Group(), promotes_inputs=['x'], promotes_outputs=['y'])
        G1.add_subsystem('C1_1', PathCompEx(), promotes_inputs=['x'])
        G1.add_subsystem('C1_2', PathCompEx(), promotes_outputs=['y'])
        G1.connect('C1_1.y', 'C1_2.x')

        G2 = G.add_subsystem('G2', Group(), promotes_inputs=['x'])
        G2.add_subsystem('C2_1', PathCompEx(), promotes_inputs=['x'])
        G2.add_subsystem('C2_2', PathCompEx(), promotes_outputs=['y'])
        G2.connect('C2_1.y', 'C2_2.x')

        model.add_subsystem('C3', PathCompEx())
        model.add_subsystem('C4', PathCompEx())

        model.connect('G.y', 'C3.x')
        model.connect('G.G2.y', 'C4.x')

        prob.setup()
        prob.run_model()

        self.assertEqual(prob['C3.y'], 'indep/G.G1.C1_1/G.G1.C1_2/C3/')
        self.assertEqual(prob['C4.y'], 'indep/G.G2.C2_1/G.G2.C2_2/C4/')

        prob['indep.x'] = 'foobar/'
        prob.run_model()

        self.assertEqual(prob['C3.y'], 'foobar/G.G1.C1_1/G.G1.C1_2/C3/')
        self.assertEqual(prob['C4.y'], 'foobar/G.G2.C2_1/G.G2.C2_2/C4/')

    def test_obj_pass(self):
        prob = Problem()
        model = prob.model

        indep = model.add_subsystem('indep', IndepVarComp(), promotes_outputs=['x'])
        indep.add_discrete_output('x', _DiscreteVal(19))

        G = model.add_subsystem('G', ParallelGroup(), promotes_inputs=['x'])

        G1 = G.add_subsystem('G1', Group(), promotes_inputs=['x'], promotes_outputs=['y'])
        G1.add_subsystem('C1_1', ObjAdderCompEx(_DiscreteVal(5)), promotes_inputs=['x'])
        G1.add_subsystem('C1_2', ObjAdderCompEx(_DiscreteVal(7)), promotes_outputs=['y'])
        G1.connect('C1_1.y', 'C1_2.x')

        G2 = G.add_subsystem('G2', Group(), promotes_inputs=['x'])
        G2.add_subsystem('C2_1', ObjAdderCompEx(_DiscreteVal(1)), promotes_inputs=['x'])
        G2.add_subsystem('C2_2', ObjAdderCompEx(_DiscreteVal(11)), promotes_outputs=['y'])
        G2.connect('C2_1.y', 'C2_2.x')

        model.add_subsystem('C3', ObjAdderCompEx(_DiscreteVal(9)))
        model.add_subsystem('C4', ObjAdderCompEx(_DiscreteVal(21)))

        model.connect('G.y', 'C3.x')
        model.connect('G.G2.y', 'C4.x')

        prob.setup()
        prob.run_model()

        self.assertEqual(prob['C3.y'].getval(), 40)
        self.assertEqual(prob['C4.y'].getval(), 52)

        def _var_iter(obj):
            name = obj['name']
            if 'children' in obj:
                for c in obj['children']:
                    for vname in _var_iter(c):
                        if name:
                            yield '.'.join((name, vname))
                        else:
                            yield vname
            else:
                yield name

        # add a test to see if discrete vars show up in view_model
        data = _get_viewer_data(prob)
        findvars = [
            'indep.x',
            'G.G1.C1_1.x',
            'G.G1.C1_1.y',
            'G.G1.C1_2.x',
            'G.G1.C1_2.y',
            'G.G2.C2_1.x',
            'G.G2.C2_1.y',
            'G.G2.C2_2.x',
            'G.G2.C2_2.y',
            'C3.x',
            'C3.y',
            'C4.x',
            'C4.y',
        ]
        vnames = list(_var_iter(data['tree']))
        self.assertTrue(sorted(findvars), sorted(vnames))


class DiscreteFeatureTestCase(unittest.TestCase):
    def test_feature_discrete(self):
        import numpy as np
        from openmdao.api import Problem, IndepVarComp, ExplicitComponent

        class BladeSolidity(ExplicitComponent):
            def setup(self):

                # Continuous Inputs
                self.add_input('r_m', 1.0, units="ft", desc="Mean radius")
                self.add_input('chord', 1.0, units="ft", desc="Chord length")

                # Discrete Inputs
                self.add_discrete_input('num_blades', 2, desc="Number of blades")

                # Continuous Outputs
                self.add_output('blade_solidity', 0.0, desc="Blade solidity")

            def compute(self, inputs, outputs, discrete_inputs, discrete_outputs):

                num_blades = discrete_inputs['num_blades']
                chord = inputs['chord']
                r_m = inputs['r_m']

                outputs['blade_solidity'] = chord / (2.0 * np.pi * r_m / num_blades)

        # build the model
        prob = Problem()
        indeps = prob.model.add_subsystem('indeps', IndepVarComp(), promotes=['*'])
        indeps.add_output('r_m', 3.2, units="ft")
        indeps.add_output('chord', .3, units='ft')
        indeps.add_discrete_output('num_blades', 2)

        prob.model.add_subsystem('SolidityComp', BladeSolidity(),
                                 promotes_inputs=['r_m', 'chord', 'num_blades'])

        prob.setup()
        prob.run_model()

        # minimum value
        assert_rel_error(self, prob['SolidityComp.blade_solidity'], 0.02984155, 1e-4)


if __name__ == "__main__":
    unittest.main()
