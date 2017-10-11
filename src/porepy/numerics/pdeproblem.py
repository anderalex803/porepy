import numpy as np
import scipy.sparse as sps

from porepy.params.data import Parameters
from porepy.params import tensor, bc
from porepy.fracs import meshing
from porepy.numerics.fv import fvutils, tpfa, mass_matrix, source
from porepy.numerics.fv.transport import upwind, upwind_coupling
from porepy.numerics import pdesolver
from porepy.numerics.mixed_dim import coupler
from porepy.viz.exporter import export_vtk, export_pvd


class PdeProblem():
    def __init__(self, physics='transport'):
        self.physics = physics
        self._data = dict()
        self._set_data()
        self._solver = self.solver()
        self._solver.parameters['store_results'] = True
        self.parameters = {'file_name': physics}
        self.parameters['folder_name'] = 'results'

    def data(self):
        return self._data

    def _set_data(self):
        for _, d in self.grid():
            d['deltaT'] = self.time_step()

    def solve(self):
        return self._solver.solve()

    def step(self):
        return self._solver.step()

    def update(self, t):
        for g, d in self.grid():
            d['problem'].update(t)

    def reassemble(self):
        return self._solver.reassemble()

    def solver(self):
        return pdesolver.Implicit(self)

    def advective_disc(self):
        advection_discr = upwind.Upwind(physics=self.physics)
        advection_coupling = upwind_coupling.UpwindCoupling(advection_discr)
        advection_solver = coupler.Coupler(advection_discr, advection_coupling)
        return advection_solver

    def diffusive_disc(self):
        diffusive_discr = tpfa.TpfaMultiDim(physics=self.physics)
        return diffusive_discr

    def source_disc(self):
        return source.IntegralMultiDim(physics=self.physics)

    def space_disc(self):
        return self.advective_disc(), self.diffusive_disc(), self.source_disc()

    def time_disc(self):
        """
        Returns the flux discretization.
        """
        mass_matrix_discr = mass_matrix.MassMatrix()
        multi_dim_discr = coupler.Coupler(mass_matrix_discr)
        return multi_dim_discr

    def initial_condition(self):
        for _, d in self.grid():
            d[self.physics] = d['problem'].initial_condition()

        global_variable = self.time_disc().merge(self.grid(), self.physics)
        return global_variable

    def grid(self):
        raise NotImplementedError('subclass must overload function grid()')

    def time_step(self):
        return 1.0

    def end_time(self):
        return 1.0

    def save(self, save_every=1):
        variables = self.data()[self.physics][::save_every]
        times = np.array(self.data()['times'])[::save_every]
        folder = self.parameters['folder_name']
        f_name = self.parameters['file_name']

        for i, p in enumerate(variables):
            self.time_disc().split(self.grid(), self.physics, p)
            data_to_plot = [self.physics]
            export_vtk(
                self.grid(), f_name, data_to_plot, time_step=i, folder=folder)

        export_pvd(
            self.grid(), self.parameters['file_name'], times, folder=folder)


class PdeProblemData():
    def __init__(self, g, data, physics='transport'):
        self._g = g
        self._data = data
        self.physics = physics
        self._set_data()

    def update(self, t):
        source = self.source(t)
        bc_val = self.bc_val(t)
        self.data()['param'].set_source(self.physics, source)
        self.data()['param'].set_bc_val(self.physics, bc_val)

    def bc(self):
        dir_bound = np.array([])
        return bc.BoundaryCondition(self.grid(), dir_bound,
                                    ['dir'] * dir_bound.size)

    def bc_val(self, t):
        return np.zeros(self.grid().num_faces)

    def initial_condition(self):
        return np.zeros(self.grid().num_cells)

    def source(self, t):
        return np.zeros(self.grid().num_cells)

    def data(self):
        return self._data

    def grid(self):
        return self._g

    def porosity(self):
        return np.ones(self.grid().num_cells)

    def diffusivity(self):
        kxx = np.ones(self.grid().num_cells)
        return tensor.SecondOrder(self.grid().dim, kxx)

    def _set_data(self):
        if 'param' not in self._data:
            self._data['param'] = Parameters(self.grid())
        self._data['param'].set_tensor(self.physics, self.diffusivity())
        self._data['param'].set_porosity(self.porosity())
        self._data['param'].set_bc(self.physics, self.bc())
        self._data['param'].set_bc_val(self.physics, self.bc_val(0.0))
        self._data['param'].set_source(self.physics, self.source(0.0))
