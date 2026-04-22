"""
Factory Profit Maximization - Linear Programming Model

Problem:
A factory produces products A and B.
- Product A: 2kg material X + 1kg material Y, profit = 300 yuan/unit
- Product B: 1kg material X + 2kg material Y, profit = 400 yuan/unit
- Daily supply: 100kg material X, 120kg material Y

Objective: Maximize daily profit
"""

import numpy as np

def solve_factory_optimization():
    """
    Solve the linear programming problem using corner point method.
    
    Mathematical Model:
    Variables: x = units of product A, y = units of product B
    Objective: Maximize P = 300x + 400y
    Constraints:
        2x + y <= 100  (Material X constraint)
        x + 2y <= 120  (Material Y constraint)
        x, y >= 0
    """
    
    print("=" * 60)
    print("LINEAR PROGRAMMING: FACTORY PROFIT MAXIMIZATION")
    print("=" * 60)

    print("\n--- PROBLEM SETUP ---")
    print("Product A: 2kg X + 1kg Y, profit = 300 yuan/unit")
    print("Product B: 1kg X + 2kg Y, profit = 400 yuan/unit")
    print("Supply: 100kg X, 120kg Y")

    print("\n--- MATHEMATICAL MODEL ---")
    print(f"Objective: Maximize P = 300x + 400y")
    print(f"Subject to:")
    print(f"  2x + y <= 100  (Material X constraint)")
    print(f"  x + 2y <= 120  (Material Y constraint)")
    print(f"  x, y >= 0")

    # Corner point method: find all intersection points of constraints
    print("\n--- FINDING CORNER POINTS ---")

    # Define all candidate corner points
    points = [
        (0, 0, "Origin"),
        (50, 0, "X-intercept of Material X constraint"),
        (0, 60, "Y-intercept of Material Y constraint"),
    ]

    # Point 4: Intersection of 2x + y = 100 and x + 2y = 120
    # Solving the system:
    # 2x + y = 100  -> y = 100 - 2x
    # x + 2y = 120  -> x + 2(100 - 2x) = 120
    #                 x + 200 - 4x = 120
    #                 -3x = -80
    #                 x = 80/3 ≈ 26.67
    #                 y = 100 - 2(80/3) = 100 - 160/3 = 140/3 ≈ 46.67
    x_intersect = 80 / 3
    y_intersect = 140 / 3
    points.append((x_intersect, y_intersect, "Intersection of two constraints"))

    # Additional intercepts to check
    points.append((0, 100, "Y-intercept of Material X constraint"))
    points.append((120, 0, "X-intercept of Material Y constraint"))

    # Filter points that satisfy all constraints
    print("\n--- EVALUATING FEASIBLE CORNER POINTS ---")
    feasible_points = []
    
    for x, y, desc in points:
        # Calculate material usage
        mat_x = 2 * x + y
        mat_y = x + 2 * y
        # Calculate profit
        profit = 300 * x + 400 * y
        # Check feasibility
        feasible = (x >= 0 and y >= 0 and 
                   mat_x <= 100 + 1e-6 and 
                   mat_y <= 120 + 1e-6)
        
        print(f"{desc:35} ({x:6.2f}, {y:6.2f}) | X:{mat_x:6.2f} Y:{mat_y:6.2f} | Profit:{profit:8.2f} | Feasible:{feasible}")
        
        if feasible:
            feasible_points.append((x, y, profit, desc))

    # Find maximum
    print("\n" + "=" * 60)
    print("OPTIMAL SOLUTION:")
    print("=" * 60)
    
    if feasible_points:
        # Select point with maximum profit
        best = max(feasible_points, key=lambda p: p[2])
        x_opt, y_opt, profit_opt, desc_opt = best
        
        print(f"Optimal point: {desc_opt}")
        print(f"Product A (x): {x_opt:.2f} units")
        print(f"Product B (y): {y_opt:.2f} units")
        print(f"Maximum Profit: {profit_opt:.2f} yuan")
        
        print("\n--- RESOURCE USAGE ---")
        mat_x_used = 2 * x_opt + y_opt
        mat_y_used = x_opt + 2 * y_opt
        
        print(f"Material X used: {mat_x_used:.2f} kg / 100 kg (remaining: {100 - mat_x_used:.2f} kg)")
        print(f"Material Y used: {mat_y_used:.2f} kg / 120 kg (remaining: {120 - mat_y_used:.2f} kg)")
        
        # Verify constraints are satisfied
        print("\n--- CONSTRAINT VERIFICATION ---")
        x_constraint = 2 * x_opt + y_opt
        y_constraint = x_opt + 2 * y_opt
        x_satisfied = x_constraint <= 100 + 1e-6
        y_satisfied = y_constraint <= 120 + 1e-6
        nonnegativity = x_opt >= 0 and y_opt >= 0
        
        print(f"2x + y <= 100: {x_constraint:.2f} <= 100 → {x_satisfied}")
        print(f"x + 2y <= 120: {y_constraint:.2f} <= 120 → {y_satisfied}")
        print(f"x >= 0, y >= 0: ({x_opt:.2f} >= 0, {y_opt:.2f} >= 0) → {nonnegativity}")
        
        all_satisfied = x_satisfied and y_satisfied and nonnegativity
        print(f"\nAll constraints satisfied: {all_satisfied}")
        
        return {
            'x': x_opt,
            'y': y_opt,
            'profit': profit_opt,
            'material_x_used': mat_x_used,
            'material_y_used': mat_y_used,
            'all_constraints_satisfied': all_satisfied
        }
    else:
        print("No feasible solution found!")
        return None

if __name__ == "__main__":
    solution = solve_factory_optimization()
