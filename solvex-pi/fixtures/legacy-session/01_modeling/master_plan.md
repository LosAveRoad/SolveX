# Master Plan

## Overview
Multi-model strategy for the legacy regression fixture.

## Model 1: Baseline Linear Program
### Purpose
Establish a baseline.
### Mathematical Formulation
min c^T x s.t. Ax <= b
### Solution Strategy
scipy.optimize.linprog
### Expected Outputs
results.csv, fig1.png
### Validation
Check constraints.

## Model 2: Bayesian Sensitivity
### Purpose
Quantify uncertainty.
### Mathematical Formulation
Posterior p(theta|y)
### Solution Strategy
MCMC sampling
### Expected Outputs
posterior.csv, fig2.png
### Validation
Convergence diagnostics.

## Integration
Combine both models.
