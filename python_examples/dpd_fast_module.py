#!/usr/bin/env python3
# dpd_fast_module.py

#------------------------------------------------------------------------------------------------#
# This software was written in 2016/17                                                           #
# by Michael P. Allen <m.p.allen@warwick.ac.uk>/<m.p.allen@bristol.ac.uk>                        #
# and Dominic J. Tildesley <dominic.tildesley@epfl.ch> ("the authors"),                          #
# to accompany the book "Computer Simulation of Liquids", second edition, 2017 ("the text"),     #
# published by Oxford University Press ("the publishers").                                       #
#                                                                                                #
# LICENCE                                                                                        #
# Creative Commons CC0 Public Domain Dedication.                                                 #
# To the extent possible under law, the authors have dedicated all copyright and related         #
# and neighboring rights to this software to the PUBLIC domain worldwide.                        #
# This software is distributed without any warranty.                                             #
# You should have received a copy of the CC0 Public Domain Dedication along with this software.  #
# If not, see <http://creativecommons.org/publicdomain/zero/1.0/>.                               #
#                                                                                                #
# DISCLAIMER                                                                                     #
# The authors and publishers make no warranties about the software, and disclaim liability       #
# for all uses of the software, to the fullest extent permitted by applicable law.               #
# The authors and publishers do not recommend use of this software for any purpose.              #
# It is made freely available, solely to clarify points made in the text. When using or citing   #
# the software, you should not imply endorsement by the authors or publishers.                   #
#------------------------------------------------------------------------------------------------#

"""Dissipative particle dynamics module (fast version)."""

class PotentialType:
    """A composite variable for interactions."""

    def __init__(self, pot, vir, lap):
        self.pot = pot # the potential energy cut-and-shifted at r_cut
        self.vir = vir # the virial
        self.lap = lap # the Laplacian

    def __add__(self, other):
        pot = self.pot +  other.pot
        vir = self.vir +  other.vir
        lap = self.lap +  other.lap

        return PotentialType(pot,vir,lap)

def introduction():
    """Prints out introductory statements at start of run."""

    print('DPD soft potential')
    print('Diameter, r_cut = 1')
    print('Fast version built around NumPy routines')

def conclusion():
    """Prints out concluding statements at end of run."""

    print('Program ends')

def force ( box, a, r ):
    """Takes in box, strength parameter, and coordinate array, and calculates forces and potentials etc.

    Also returns list of pairs in range for use by the thermalization algorithm.
    Attempts to use NumPy functions.
    """

    import numpy as np

    # It is assumed that positions are in units where box = 1

    n,d = r.shape
    assert d==3, 'Dimension error in force'

    total = PotentialType ( pot=0.0, vir=0.0, lap=0.0 )
    f = np.zeros_like(r)
    pairs = []

    for i in range(n-1):
        rij = r[i,:]-r[i+1:,:]           # Separation vectors for j>i
        rij = rij - np.rint(rij)         # Periodic boundary conditions in box=1 units
        rij = rij * box                  # Now in sigma=1 units
        rij_sq   = np.sum(rij**2,axis=1) # Squared separations for j>1
        rij_mag  = np.sqrt(rij_sq)       # Separations for j>i
        rij_hat  = rij / rij_mag[:,np.newaxis]        # Unit separation vectors
        in_range = rij_sq < 1.0                       # Set flags for within cutoff
        wij      = np.where(in_range,1.0-rij_mag,0.0) # Weight functions
        pot = 0.5 * wij**2                # Pair potentials
        vir = wij * rij_mag               # Pair virials
        lap = 3.0-2.0/rij_mag             # Pair Laplacians
        fij = wij[:,np.newaxis] * rij_hat # Pair forces

        total = total + PotentialType ( pot=sum(pot), vir=sum(vir), lap=sum(lap) )
        f[i,:] = f[i,:] + np.sum(fij,axis=0)
        f[i+1:,:] = f[i+1:,:] - fij
        jvals = np.extract(in_range,np.arange(i+1,n))
        pairs = pairs + [ (i,j,rij_mag[j-i-1],rij_hat[j-i-1,:]) for j in jvals ]

    # Multiply results by numerical factors
    total.pot = total.pot * a
    total.vir = total.vir * a / 3.0
    total.lap = total.lap * a * 2.0
    f         = f * a

    return total, f, pairs

def lowe ( box, temperature, gamma_step, v, pairs ):
    """Updates velocities using pairwise Lowe-Andersen thermostat.

    Uses a simple Python loop, which will be slow
    (but necessary, since the operations are supposed to be sequential).
    """

    # It is assumed that positions in the array r are in units where box = 1
    # and that the array ij contains a list of all pairs within range

    import numpy as np

    v_std = np.sqrt(2*temperature) # Standard deviation for relative velocity distribution

    for p in np.random.permutation(len(pairs)):
        zeta = np.random.rand()
        if zeta<gamma_step:
            (i,j,rij_mag,rij_hat) = pairs[p]
            vij    = v[i,:] - v[j,:]             # Relative velocity vector
            v_old  = np.dot(vij,rij_hat)         # Projection of vij along separation
            v_new  = v_std*np.random.randn()     # New projection of vij along separation
            vij    = ( v_new - v_old ) * rij_hat # Change in relative velocity
            v[i,:] = v[i,:] + 0.5 * vij          # New i-velocity
            v[j,:] = v[j,:] - 0.5 * vij          # New j-velocity

    return v

def shardlow ( box, temperature, gamma_step, v, pairs ):
    """Updates velocities using Shardlow integration algorithm.

    Uses a simple Python loop, which will be slow
    (but necessary, since the operations are supposed to be sequential).
    However, we do use NumPy to do as much preliminary work as possible.
    """

    # It is assumed that positions in the array r are in units where box = 1
    # and that the array ij contains a list of all pairs within range

    import numpy as np

    sqrt_gamma_step = np.sqrt(gamma_step)
    v_std = np.sqrt(2*temperature) # Standard deviation for relative velocity distribution

    for p in np.random.permutation(len(pairs)):
        (i,j,rij_mag,rij_hat) = pairs[p]

        wij       = 1 - rij_mag           # Weight function
        sqrt_prob = sqrt_gamma_step * wij # sqrt of p-factor
        prob      = sqrt_prob**2          # p-factor
        v_new     = v_std*np.random.randn()

        # First half step
        vij    = v[i,:] - v[j,:]                            # Relative velocity vector
        v_old  = np.dot(vij,rij_hat)                        # Projection of vij along separation
        vij    = ( sqrt_prob*v_new - prob*v_old ) * rij_hat # Change in relative velocity
        v[i,:] = v[i,:] + 0.5 * vij                         # New i-velocity
        v[j,:] = v[j,:] - 0.5 * vij                         # New j-velocity

        # Second half step
        vij    = v[i,:] - v[j,:]                                     # Relative velocity vector
        v_old  = np.dot(vij,rij_hat)                                 # Projection of vij along separation
        vij    = ( sqrt_prob*v_new - prob*v_old ) * rij_hat/(1+prob) # Change in relative velocity
        v[i,:] = v[i,:] + 0.5 * vij                                  # New i-velocity
        v[j,:] = v[j,:] - 0.5 * vij                                  # New j-velocity

    return v

def p_approx ( a, rho, temperature ):
    """Returns approximate pressure."""

    # This expression is given by Groot and Warren, J Chem Phys 107, 4423 (1997), alpha = 0.101
    # This is the revised formula due to Liyana-Arachchi, Jamadagni, Elke, Koenig, Siepmann,
    # J Chem Phys 142, 044902 (2015)

    import numpy as np

    c1, c2 = 0.0802, 0.7787
    b = [1.705e-8,-2.585e-6,1.556e-4,-4.912e-3,9.755e-2]
    b2 = np.polyval (b,a)                                           # This is B2/a, eqn (10) of above paper
    alpha = b2 / ( 1 + rho**3 ) + ( c1*rho**2 ) / ( 1 + c2*rho**2 ) # This is eqn (14) of above paper
    return rho * temperature + alpha * a * rho**2