"""
Interpolate using a third order Lagrange polynomial.

Based on NPSS implementation.
"""
import numpy as np

from openmdao.components.interp_util.interp_algorithm import InterpAlgorithm, \
    InterpAlgorithmSemi, InterpAlgorithmFixed


class InterpLagrange3(InterpAlgorithm):
    """
    Interpolate using a third order Lagrange polynomial.

    Parameters
    ----------
    grid : tuple(ndarray)
        Tuple containing x grid locations for this dimension and all subtable dimensions.
    values : ndarray
        Array containing the table values for all dimensions.
    interp : class
        Interpolation class to be used for subsequent table dimensions.
    **kwargs : dict
        Interpolator-specific options to pass onward.
    """

    def __init__(self, grid, values, interp, **kwargs):
        """
        Initialize table and subtables.
        """
        super().__init__(grid, values, interp, **kwargs)
        self.k = 4
        self._name = 'lagrange3'

    def interpolate(self, x, idx, slice_idx):
        """
        Compute the interpolated value over this grid dimension.

        Parameters
        ----------
        x : ndarray
            The coordinates to sample the gridded data at. First array element is the point to
            interpolate here. Remaining elements are interpolated on sub tables.
        idx : int
            Interval index for x.
        slice_idx : list of <slice>
            Slice object containing indices of data points requested by parent interpolating
            tables.

        Returns
        -------
        ndarray
            Interpolated values.
        ndarray
            Derivative of interpolated values with respect to this independent and child
            independents.
        ndarray
            Derivative of interpolated values with respect to values for this and subsequent table
            dimensions.
        ndarray
            Derivative of interpolated values with respect to grid for this and subsequent table
            dimensions.
        """
        grid = self.grid
        subtable = self.subtable

        # Complex Step
        if self.values.dtype == complex:
            dtype = self.values.dtype
        else:
            dtype = x.dtype

        # Shift if we don't have 2 points on each side.
        ngrid = len(grid)
        if idx > ngrid - 3:
            idx = ngrid - 3
        elif idx == 0:
            idx = 1

        derivs = np.empty(len(x))

        p1 = grid[idx - 1]
        p2 = grid[idx]
        p3 = grid[idx + 1]
        p4 = grid[idx + 2]

        xx1 = x[0] - p1
        xx2 = x[0] - p2
        xx3 = x[0] - p3
        xx4 = x[0] - p4

        c12 = 1.0 / (p1 - p2)
        c13 = 1.0 / (p1 - p3)
        c14 = 1.0 / (p1 - p4)
        c23 = 1.0 / (p2 - p3)
        c24 = 1.0 / (p2 - p4)
        c34 = 1.0 / (p3 - p4)

        if subtable is not None:
            # Interpolate between values that come from interpolating the subtables in the
            # subsequent dimensions.
            nx = len(x)
            slice_idx.append(slice(idx - 1, idx + 3))

            tshape = self.values[tuple(slice_idx)].shape
            nshape = list(tshape[:-nx])
            nshape.append(nx)
            derivs = np.empty(tuple(nshape), dtype=dtype)

            subval, subderiv, _, _ = subtable.evaluate(x[1:], slice_idx=slice_idx)

            q1 = subval[..., 0] * (c12 * c13 * c14)
            q2 = subval[..., 1] * (c12 * c23 * c24)
            q3 = subval[..., 2] * (c13 * c23 * c34)
            q4 = subval[..., 3] * (c14 * c24 * c34)

            dq1_dsub = subderiv[..., 0, :] * (c12 * c13 * c14)
            dq2_dsub = subderiv[..., 1, :] * (c12 * c23 * c24)
            dq3_dsub = subderiv[..., 2, :] * (c13 * c23 * c34)
            dq4_dsub = subderiv[..., 3, :] * (c14 * c24 * c34)

            derivs[..., 1:] = xx4 * (xx3 * (dq1_dsub * xx2 - dq2_dsub * xx1) +
                                     dq3_dsub * xx1 * xx2) - dq4_dsub * xx1 * xx2 * xx3

        else:
            values = self.values[tuple(slice_idx)]

            nshape = list(values.shape[:-1])
            nshape.append(1)
            derivs = np.empty(tuple(nshape), dtype=dtype)

            q1 = values[..., idx - 1] * (c12 * c13 * c14)
            q2 = values[..., idx] * (c12 * c23 * c24)
            q3 = values[..., idx + 1] * (c13 * c23 * c34)
            q4 = values[..., idx + 2] * (c14 * c24 * c34)

        derivs[..., 0] = q1 * (x[0] * (3.0 * x[0] - 2.0 * (p4 + p3 + p2)) +
                               p4 * (p2 + p3) + p2 * p3) - \
            q2 * (x[0] * (3.0 * x[0] - 2.0 * (p4 + p3 + p1)) +
                  p4 * (p1 + p3) + p1 * p3) + \
            q3 * (x[0] * (3.0 * x[0] - 2.0 * (p4 + p2 + p1)) +
                  p4 * (p2 + p1) + p2 * p1) - \
            q4 * (x[0] * (3.0 * x[0] - 2.0 * (p3 + p2 + p1)) +
                  p1 * (p2 + p3) + p2 * p3)

        return xx4 * (xx3 * (q1 * xx2 - q2 * xx1) + q3 * xx1 * xx2) - q4 * xx1 * xx2 * xx3, \
            derivs, None, None


class InterpLagrange3Semi(InterpAlgorithmSemi):
    """
    Interpolate on a semi structured grid using a second order Lagrange polynomial.

    Parameters
    ----------
    grid : tuple(ndarray)
        Tuple containing ndarray of x grid locations for each table dimension.
    values : ndarray
        Array containing the values at all points in grid.
    interp : class
        Interpolation class to be used for subsequent table dimensions.
    extrapolate : bool
        When False, raise an error if extrapolation occurs in this dimension.
    compute_d_dvalues : bool
        When True, compute gradients with respect to the table values.
    idx : list or None
        Maps values to their indices in the training data input. Only used during recursive
        calls.
    idim : int
        Integer corresponding to table depth. Used for error messages.
    **kwargs : dict
        Interpolator-specific options to pass onward.
    """

    def __init__(self, grid, values, interp, extrapolate=True, compute_d_dvalues=False, idx=None,
                 idim=0, **kwargs):
        """
        Initialize table and subtables.
        """
        super().__init__(grid, values, interp, extrapolate=extrapolate,
                         compute_d_dvalues=compute_d_dvalues, idx=idx, idim=idim, **kwargs)
        self.k = 4
        self._name = 'lagrange3'

    def interpolate(self, x):
        """
        Compute the interpolated value over this grid dimension.

        Parameters
        ----------
        x : ndarray
            Coordinate of the point being interpolated. First element is component in this
            dimension. Remaining elements are interpolated on sub tables.

        Returns
        -------
        ndarray
            Interpolated values.
        ndarray
            Derivative of interpolated values with respect to this independent and child
            independents.
        tuple(ndarray, list)
            Derivative of interpolated values with respect to values for this and subsequent table
            dimensions. Second term is the indices into the value array.
        bool
            True if the coordinate is extrapolated in this dimension.
        """
        grid = self.grid
        subtables = self.subtables

        idx, flag = self.bracket(x[0])
        extrap = flag != 0

        # Complex Step
        if self.values.dtype == complex:
            dtype = self.values.dtype
        else:
            dtype = x.dtype

        # Shift if we don't have 2 points on each side.
        ngrid = len(grid)
        if idx > ngrid - 3:
            idx = ngrid - 3
        elif idx == 0:
            idx = 1

        derivs = np.empty(len(x), dtype=dtype)

        if subtables is not None:
            # Interpolate between values that come from interpolating the subtables in the
            # subsequent dimensions.
            val0, dx0, dvalue0, flag0 = subtables[idx - 1].interpolate(x[1:])
            val1, dx1, dvalue1, flag1 = subtables[idx].interpolate(x[1:])
            val2, dx2, dvalue2, flag2 = subtables[idx + 1].interpolate(x[1:])
            val3, dx3, dvalue3, flag3 = subtables[idx + 2].interpolate(x[1:])

            # Extrapolation detection.
            flags = (flag0, flag1, flag2, flag3)
            if extrap or flags == (False, False, False, False):
                # If we are already extrapolating, no change needed.
                # If no sub-points are extrapolating, no change needed.
                pass
            elif flags == (False, False, False, True) and idx > 0:
                # We are near the right edge of our sub-region, so slide to the left.
                idx -= 1
                val_a, dx_a, dvalue_a, flag_a = subtables[idx - 1].interpolate(x[1:])
                if flag_a:
                    # Nothing we can do; there just aren't enough points here.
                    idx += 1
                    extrap = True
                else:
                    val3, dx3, dvalue3 = val2, dx2, dvalue2
                    val2, dx2, dvalue2 = val1, dx1, dvalue1
                    val1, dx1, dvalue1 = val0, dx0, dvalue0
                    val0, dx0, dvalue0 = val_a, dx_a, dvalue_a
            elif flags == (True, False, False, False) and idx < ngrid - 3:
                # We are near the left edge of our sub-region, so slide to the right.
                idx += 1
                val_a, dx_a, dvalue_a, flag_a = subtables[idx + 2].interpolate(x[1:])
                if flag_a:
                    # Nothing we can do; there just aren't enough points here.
                    idx -= 1
                    extrap = True
                else:
                    val0, dx0, dvalue0 = val1, dx1, dvalue1
                    val1, dx1, dvalue1 = val2, dx2, dvalue2
                    val2, dx2, dvalue2 = val3, dx3, dvalue3
                    val3, dx3, dvalue3 = val_a, dx_a, dvalue_a
            else:
                # All other cases, we are in an extrapolation sub-region.
                extrap = True

        p1 = grid[idx - 1]
        p2 = grid[idx]
        p3 = grid[idx + 1]
        p4 = grid[idx + 2]

        xx1 = x[0] - p1
        xx2 = x[0] - p2
        xx3 = x[0] - p3
        xx4 = x[0] - p4

        c12 = p1 - p2
        c13 = p1 - p3
        c14 = p1 - p4
        c23 = p2 - p3
        c24 = p2 - p4
        c34 = p3 - p4

        fact1 = 1.0 / (c12 * c13 * c14)
        fact2 = 1.0 / (c12 * c23 * c24)
        fact3 = 1.0 / (c13 * c23 * c34)
        fact4 = 1.0 / (c14 * c24 * c34)

        if subtables is not None:

            derivs = np.empty(len(dx0) + 1, dtype=dtype)

            q1 = val0 * fact1
            q2 = val1 * fact2
            q3 = val2 * fact3
            q4 = val3 * fact4

            dq1_dsub = dx0 * fact1
            dq2_dsub = dx1 * fact2
            dq3_dsub = dx2 * fact3
            dq4_dsub = dx3 * fact4

            derivs[1:] = xx4 * (xx3 * (dq1_dsub * xx2 - dq2_dsub * xx1) +
                                dq3_dsub * xx1 * xx2) - dq4_dsub * xx1 * xx2 * xx3

            d_value = None
            if self._compute_d_dvalues:
                dvalue0, idx0 = dvalue0
                dvalue1, idx1 = dvalue1
                dvalue2, idx2 = dvalue2
                dvalue3, idx3 = dvalue3
                n = len(dvalue0)

                d_value = np.empty(n * 4, dtype=dtype)
                d_value[:n] = dvalue0 * xx2 * xx3 * xx4 * fact1
                d_value[n:n * 2] = -dvalue1 * xx1 * xx3 * xx4 * fact2
                d_value[n * 2:n * 3] = dvalue2 * xx1 * xx2 * xx4 * fact3
                d_value[n * 3:n * 4] = -dvalue3 * xx1 * xx2 * xx3 * fact4

                idx0.extend(idx1)
                idx0.extend(idx2)
                idx0.extend(idx3)
                d_value = (d_value, idx0)

        else:
            values = self.values
            derivs = np.empty(1, dtype=dtype)

            q1 = values[idx - 1] * fact1
            q2 = values[idx] * fact2
            q3 = values[idx + 1] * fact3
            q4 = values[idx + 2] * fact4

            d_value = None
            if self._compute_d_dvalues:
                d_value = np.empty(4, dtype=dtype)
                d_value[0] = xx2 * xx3 * xx4 * fact1
                d_value[1] = -xx1 * xx3 * xx4 * fact2
                d_value[2] = xx1 * xx2 * xx4 * fact3
                d_value[3] = -xx1 * xx2 * xx3 * fact4

                d_value = (d_value,
                           [self._idx[idx - 1], self._idx[idx],
                            self._idx[idx + 1], self._idx[idx + 2]])

        derivs[0] = q1 * (x[0] * (3.0 * x[0] - 2.0 * (p4 + p3 + p2)) +
                          p4 * (p2 + p3) + p2 * p3) - \
            q2 * (x[0] * (3.0 * x[0] - 2.0 * (p4 + p3 + p1)) +
                  p4 * (p1 + p3) + p1 * p3) + \
            q3 * (x[0] * (3.0 * x[0] - 2.0 * (p4 + p2 + p1)) +
                  p4 * (p2 + p1) + p2 * p1) - \
            q4 * (x[0] * (3.0 * x[0] - 2.0 * (p3 + p2 + p1)) +
                  p1 * (p2 + p3) + p2 * p3)

        return xx4 * (xx3 * (q1 * xx2 - q2 * xx1) + q3 * xx1 * xx2) - q4 * xx1 * xx2 * xx3, \
            derivs, d_value, extrap


class InterpLagrange3D(InterpAlgorithmFixed):
    """
    Interpolate on a fixed 3D grid using a third order Lagrange polynomial.

    Parameters
    ----------
    grid : tuple(ndarray)
        Tuple containing x grid locations for this dimension and all subtable dimensions.
    values : ndarray
        Array containing the table values for all dimensions.
    interp : class
        Interpolation class to be used for subsequent table dimensions.
    **kwargs : dict
        Interpolator-specific options to pass onward.
    """
    def __init__(self, grid, values, interp, **kwargs):
        """
        Initialize table and subtables.
        """
        super().__init__(grid, values, interp)
        self.coeffs = {}
        self.vec_coeff = None
        self.k = 4
        self.dim = 3
        self.last_index = [0] * self.dim
        self._name = 'lagrange3D'
        self._vectorized = False

    def vectorized(self, x):
        """
        Return whether this table will be run vectorized for the given requested input.

        Parameters
        ----------
        x : float
            Value of new independent to interpolate.

        Returns
        -------
        bool
            Returns True if this table can be run vectorized.
        """
        # If we only have 1 point, use the non-vectorized implementation, which has faster
        # bracketing than the numpy version.
        return x.shape[0] > 1

    def interpolate(self, x, idx):
        """
        Compute the interpolated value.

        Parameters
        ----------
        x : ndarray
            The coordinates to sample the gridded data at. First array element is the point to
            interpolate here. Remaining elements are interpolated on sub tables.
        idx : int
            Interval index for x.

        Returns
        -------
        ndarray
            Interpolated values.
        ndarray
            Derivative of interpolated values with respect to this independent and child
            independents.
        ndarray
            Derivative of interpolated values with respect to values for this and subsequent table
            dimensions.
        ndarray
            Derivative of interpolated values with respect to grid for this and subsequent table
            dimensions.
        """
        grid = self.grid
        i_x, i_y, i_z = idx

        # Extrapolation
        # Shift if we don't have 2 points on each side.
        n = len(grid[0])
        if i_x > n - 3:
            i_x = n - 3
        elif i_x < 1:
            i_x = 1

        n = len(grid[1])
        if i_y > n - 3:
            i_y = n - 3
        elif i_y < 1:
            i_y = 1

        n = len(grid[2])
        if i_z > n - 3:
            i_z = n - 3
        elif i_z < 1:
            i_z = 1

        idx = (i_x, i_y, i_z)

        # Complex Step
        if self.values.dtype == complex:
            dtype = self.values.dtype
        else:
            dtype = x.dtype

        if idx not in self.coeffs:
            self.coeffs[idx] = self.compute_coeffs(idx)
        a = self.coeffs[idx].copy()

        x, y, z = x

        # Taking powers of the "deltas" instead of the actual table inputs eliminates numerical
        # problems that arise from the scaling of each axis.
        x = x - grid[0][i_x - 1]
        y = y - grid[1][i_y - 1]
        z = z - grid[2][i_z - 1]

        # Compute interpolated value using the 64 coefficients.

        xx = np.array([1.0, x, x * x, x * x * x], dtype=dtype)
        yy = np.array([1.0, y, y * y, y * y * y], dtype=dtype)
        zz = np.array([1.0, z, z * z, z * z * z], dtype=dtype)
        val = np.einsum('ijk,i,j,k->', a, xx, yy, zz)

        # Compute derivatives using the 64 coefficients.

        a = np.empty((4, 4, 4, 3), dtype=dtype)
        a[..., 0] = self.coeffs[idx]
        a[..., 1] = self.coeffs[idx]
        a[..., 2] = self.coeffs[idx]

        dx = np.empty((4, 3), dtype=dtype)
        dy = np.empty((4, 3), dtype=dtype)
        dz = np.empty((4, 3), dtype=dtype)
        dx[:, 0] = np.array([0.0, 1.0, 2.0 * x, 3.0 * x * x])
        dy[:, 1] = np.array([0.0, 1.0, 2.0 * y, 3.0 * y * y])
        dz[:, 2] = np.array([0.0, 1.0, 2.0 * z, 3.0 * z * z])

        dx[:, 1] = xx
        dx[:, 2] = xx
        dy[:, 0] = yy
        dy[:, 2] = yy
        dz[:, 0] = zz
        dz[:, 1] = zz

        d_x = np.einsum('im,jm,km,ijkm->m', dx, dy, dz, a)

        return val, d_x, None, None

    def compute_coeffs(self, idx):
        """
        Compute the tri-lagrange3 interpolation coefficients for this block.

        Parameters
        ----------
        idx : int
            List of interval indices for x.

        Returns
        -------
        ndarray
            Interpolation coefficients.
        """
        grid = self.grid
        values = self.values
        a = np.zeros((4, 4, 4))

        i_x, i_y, i_z = idx

        x = grid[0]
        y = grid[1]
        z = grid[2]
        x1, x2, x3, x4 = x[i_x - 1:i_x + 3]
        y1, y2, y3, y4 = y[i_y - 1:i_y + 3]
        z1, z2, z3, z4 = z[i_z - 1:i_z + 3]

        cx12 = x1 - x2
        cx13 = x1 - x3
        cx14 = x1 - x4
        cx23 = x2 - x3
        cx24 = x2 - x4
        cx34 = x3 - x4

        cy12 = y1 - y2
        cy13 = y1 - y3
        cy14 = y1 - y4
        cy23 = y2 - y3
        cy24 = y2 - y4
        cy34 = y3 - y4

        cz12 = z1 - z2
        cz13 = z1 - z3
        cz14 = z1 - z4
        cz23 = z2 - z3
        cz24 = z2 - z4
        cz34 = z3 - z4

        # Normalize for numerical stability
        x2 -= x1
        x3 -= x1
        x4 -= x1

        y2 -= y1
        y3 -= y1
        y4 -= y1

        z2 -= z1
        z3 -= z1
        z4 -= z1

        termx = np.array([[x2 * x3 * x4,
                          0.0,
                          0.0,
                          0.0],
                          [x2 * x3 + x2 * x4 + x3 * x4,
                           x3 * x4,
                           x2 * x4,
                           x2 * x3],
                          [x2 + x3 + x4,
                           x3 + x4,
                           x2 + x4,
                           x2 + x3],
                          [1.0 / (cx12 * cx13 * cx14),
                           -1.0 / (cx12 * cx23 * cx24),
                           1.0 / (cx13 * cx23 * cx34),
                           -1.0 / (cx14 * cx24 * cx34)]])

        termy = np.array([[y2 * y3 * y4,
                           0.0,
                           0.0,
                           0.0],
                          [y2 * y3 + y2 * y4 + y3 * y4,
                           y3 * y4,
                           y2 * y4,
                           y2 * y3],
                          [y2 + y3 + y4,
                           y3 + y4,
                           y2 + y4,
                           y2 + y3],
                          [1.0 / (cy12 * cy13 * cy14),
                           -1.0 / (cy12 * cy23 * cy24),
                           1.0 / (cy13 * cy23 * cy34),
                           -1.0 / (cy14 * cy24 * cy34)]])

        termz = np.array([[z2 * z3 * z4,
                           0.0,
                           0.0,
                           0.0],
                          [z2 * z3 + z2 * z4 + z3 * z4,
                           z3 * z4,
                           z2 * z4,
                           z2 * z3],
                          [z2 + z3 + z4,
                           z3 + z4,
                           z2 + z4,
                           z2 + z3],
                          [1.0 / (cz12 * cz13 * cz14),
                           -1.0 / (cz12 * cz23 * cz24),
                           1.0 / (cz13 * cz23 * cz34),
                           -1.0 / (cz14 * cz24 * cz34)]])


        termx[2, :] *= -termx[3, :]
        termy[2, :] *= -termy[3, :]
        termz[2, :] *= -termz[3, :]

        termx[1, :] *= termx[3, :]
        termy[1, :] *= termy[3, :]
        termz[1, :] *= termz[3, :]

        termx[0, :] *= -termx[3, :]
        termy[0, :] *= -termy[3, :]
        termz[0, :] *= -termz[3, :]

        all_val = values[i_x - 1: i_x + 3, i_y - 1: i_y + 3, i_z - 1: i_z + 3]

        a = np.einsum("mi,nj,pk,ijk->mnp", termx, termy, termz, all_val)

        return a

    def interpolate_vectorized(self, x_vec, idx):
        """
        Compute the interpolated value.

        Parameters
        ----------
        x_vec : ndarray
            The coordinates to interpolate on this grid.
        idx : int
            List of interval indices for x.

        Returns
        -------
        ndarray
            Interpolated values.
        ndarray
            Derivative of interpolated values with respect to independents.
        ndarray
            Derivative of interpolated values with respect to values.
        ndarray
            Derivative of interpolated values with respect to grid.
        """
        grid = self.grid

        for j, i_n in enumerate(idx):

            # extrapolate low
            if -1 in i_n or 0 in i_n:
                extrap_idx = np.where(i_n < 1)[0]
                i_n[extrap_idx] = 1

            # extrapolate high
            ngrid = len(grid[j])
            if ngrid - 1 in i_n or ngrid - 2 in i_n:
                extrap_idx = np.where(i_n > ngrid - 3)[0]
                i_n[extrap_idx] = ngrid - 3

        if self.vec_coeff is None:
            self.coeffs = set()
            grid = self.grid
            self.vec_coeff = np.empty((len(grid[0]), len(grid[1]), len(grid[2]), 4, 4, 4))

        needed = set([item for item in zip(idx[0], idx[1], idx[2])])
        uncached = needed.difference(self.coeffs)
        if len(uncached) > 0:
            unc = np.array(list(uncached))
            uncached_idx = (unc[:, 0], unc[:, 1], unc[:, 2])
            a = self.compute_coeffs_vectorized(uncached_idx)
            self.vec_coeff[unc[:, 0], unc[:, 1], unc[:, 2], ...] = a
            self.coeffs = self.coeffs.union(uncached)
        a = self.vec_coeff[idx[0], idx[1], idx[2], :]

        # Taking powers of the "deltas" instead of the actual table inputs eliminates numerical
        # problems that arise from the scaling of each axis.
        i_x, i_y, i_z = idx
        x = x_vec[:, 0] - grid[0][i_x - 1]
        y = x_vec[:, 1] - grid[1][i_y - 1]
        z = x_vec[:, 2] - grid[2][i_z - 1]

        # Complex Step
        if self.values.dtype == complex:
            dtype = self.values.dtype
        else:
            dtype = x.dtype

        # Compute interpolated value using the 64 coefficients.

        vec_size = len(i_x)
        xx = np.empty((vec_size, 4), dtype=dtype)
        xx[:, 0] = 1.0
        xx[:, 1] = x
        xx[:, 2] = xx[:, 1] * x
        xx[:, 3] = xx[:, 2] * x

        yy = np.empty((vec_size, 4), dtype=dtype)
        yy[:, 0] = 1.0
        yy[:, 1] = y
        yy[:, 2] = yy[:, 1] * y
        yy[:, 3] = yy[:, 2] * y

        zz = np.empty((vec_size, 4), dtype=dtype)
        zz[:, 0] = 1.0
        zz[:, 1] = z
        zz[:, 2] = zz[:, 1] * z
        zz[:, 3] = zz[:, 2] * z

        val = np.einsum('qijk,qi,qj,qk->q', a, xx, yy, zz)

        # Compute derivatives using the 64 coefficients.

        a = np.empty((vec_size, 4, 4, 4, 3), dtype=dtype)
        a[..., 0] = self.vec_coeff[idx[0], idx[1], idx[2], :]
        a[..., 1] = self.vec_coeff[idx[0], idx[1], idx[2], :]
        a[..., 2] = self.vec_coeff[idx[0], idx[1], idx[2], :]

        dx = np.empty((vec_size, 4, 3), dtype=dtype)
        dx[:, 0, 0] = 0.0
        dx[:, 1, 0] = 1.0
        dx[:, 2, 0] = 2.0 * x
        dx[:, 3, 0] = 3.0 * x * x
        dx[:, :, 1] = xx
        dx[:, :, 2] = xx

        dy = np.empty((vec_size, 4, 3), dtype=dtype)
        dy[:, 0, 1] = 0.0
        dy[:, 1, 1] = 1.0
        dy[:, 2, 1] = 2.0 * y
        dy[:, 3, 1] = 3.0 * y * y
        dy[:, :, 0] = yy
        dy[:, :, 2] = yy

        dz = np.empty((vec_size, 4, 3), dtype=dtype)
        dz[:, 0, 2] = 0.0
        dz[:, 1, 2] = 1.0
        dz[:, 2, 2] = 2.0 * z
        dz[:, 3, 2] = 3.0 * z * z
        dz[:, :, 0] = zz
        dz[:, :, 1] = zz

        d_x = np.einsum('qim,qjm,qkm,qijkm->qm', dx, dy, dz, a)

        return val, d_x, None, None

    def compute_coeffs_vectorized(self, idx):
        """
        Compute the tri-lagrange3 interpolation coefficients for this block.

        Parameters
        ----------
        idx : int
            List of interval indices for x.

        Returns
        -------
        ndarray
            Interpolation coefficients.
        """
        grid = self.grid
        values = self.values
        a = np.zeros((4, 4, 4))

        i_x, i_y, i_z = idx
        vec_size = len(i_x)

        x = grid[0]
        y = grid[1]
        z = grid[2]

        x1 = x[i_x - 1]
        x2 = x[i_x]
        x3 = x[i_x + 1]
        x4 = x[i_x + 2]
        y1 = y[i_y - 1]
        y2 = y[i_y]
        y3 = y[i_y + 1]
        y4 = y[i_y + 2]
        z1 = z[i_z - 1]
        z2 = z[i_z]
        z3 = z[i_z + 1]
        z4 = z[i_z + 2]

        cx12 = x1 - x2
        cx13 = x1 - x3
        cx14 = x1 - x4
        cx23 = x2 - x3
        cx24 = x2 - x4
        cx34 = x3 - x4

        cy12 = y1 - y2
        cy13 = y1 - y3
        cy14 = y1 - y4
        cy23 = y2 - y3
        cy24 = y2 - y4
        cy34 = y3 - y4

        cz12 = z1 - z2
        cz13 = z1 - z3
        cz14 = z1 - z4
        cz23 = z2 - z3
        cz24 = z2 - z4
        cz34 = z3 - z4

        # Normalize for numerical stability
        x2 -= x1
        x3 -= x1
        x4 -= x1

        y2 -= y1
        y3 -= y1
        y4 -= y1

        z2 -= z1
        z3 -= z1
        z4 -= z1

        termx = np.empty((vec_size, 4, 4))
        termx[:, 0, 0] = x2 * x3 * x4
        termx[:, 0, 1] = 0.0
        termx[:, 0, 2] = 0.0
        termx[:, 0, 3] = 0.0
        termx[:, 1, 0] = x2 * x3 + x2 * x4 + x3 * x4
        termx[:, 1, 1] = x3 * x4
        termx[:, 1, 2] = x2 * x4
        termx[:, 1, 3] = x2 * x3
        termx[:, 2, 0] = x2 + x3 + x4
        termx[:, 2, 1] = x3 + x4
        termx[:, 2, 2] = x2 + x4
        termx[:, 2, 3] = x2 + x3
        termx[:, 3, 0] = 1.0 / (cx12 * cx13 * cx14)
        termx[:, 3, 1] = -1.0 / (cx12 * cx23 * cx24)
        termx[:, 3, 2] = 1.0 / (cx13 * cx23 * cx34)
        termx[:, 3, 3] = -1.0 / (cx14 * cx24 * cx34)

        termy = np.empty((vec_size, 4, 4))
        termy[:, 0, 0] = y2 * y3 * y4
        termy[:, 0, 1] = 0.0
        termy[:, 0, 2] = 0.0
        termy[:, 0, 3] = 0.0
        termy[:, 1, 0] = y2 * y3 + y2 * y4 + y3 * y4
        termy[:, 1, 1] = y3 * y4
        termy[:, 1, 2] = y2 * y4
        termy[:, 1, 3] = y2 * y3
        termy[:, 2, 0] = y2 + y3 + y4
        termy[:, 2, 1] = y3 + y4
        termy[:, 2, 2] = y2 + y4
        termy[:, 2, 3] = y2 + y3
        termy[:, 3, 0] = 1.0 / (cy12 * cy13 * cy14)
        termy[:, 3, 1] = -1.0 / (cy12 * cy23 * cy24)
        termy[:, 3, 2] = 1.0 / (cy13 * cy23 * cy34)
        termy[:, 3, 3] = -1.0 / (cy14 * cy24 * cy34)

        termz = np.empty((vec_size, 4, 4))
        termz[:, 0, 0] = z2 * z3 * z4
        termz[:, 0, 1] = 0.0
        termz[:, 0, 2] = 0.0
        termz[:, 0, 3] = 0.0
        termz[:, 1, 0] = z2 * z3 + z2 * z4 + z3 * z4
        termz[:, 1, 1] = z3 * z4
        termz[:, 1, 2] = z2 * z4
        termz[:, 1, 3] = z2 * z3
        termz[:, 2, 0] = z2 + z3 + z4
        termz[:, 2, 1] = z3 + z4
        termz[:, 2, 2] = z2 + z4
        termz[:, 2, 3] = z2 + z3
        termz[:, 3, 0] = 1.0 / (cz12 * cz13 * cz14)
        termz[:, 3, 1] = -1.0 / (cz12 * cz23 * cz24)
        termz[:, 3, 2] = 1.0 / (cz13 * cz23 * cz34)
        termz[:, 3, 3] = -1.0 / (cz14 * cz24 * cz34)

        termx[:, 2, :] *= -termx[:, 3, :]
        termy[:, 2, :] *= -termy[:, 3, :]
        termz[:, 2, :] *= -termz[:, 3, :]

        termx[:, 1, :] *= termx[:, 3, :]
        termy[:, 1, :] *= termy[:, 3, :]
        termz[:, 1, :] *= termz[:, 3, :]

        termx[:, 0, :] *= -termx[:, 3, :]
        termy[:, 0, :] *= -termy[:, 3, :]
        termz[:, 0, :] *= -termz[:, 3, :]

        all_val = np.empty((vec_size, 4, 4, 4))
        # The only loop in this algorithm, but it doesn't seem to have much impact on time.
        # Broadcasting out the index slices would be a bit complicated.
        for j in range(vec_size):
            all_val[j, ...] = values[i_x[j] - 1: i_x[j] + 3,
                                     i_y[j] - 1: i_y[j] + 3,
                                     i_z[j] - 1: i_z[j] + 3]

        a = np.einsum("qmi,qnj,qpk,qijk->qmnp", termx, termy, termz, all_val)

        return a
