# Explore Tab

The Explore tab is a free-form viewer for derived analysis quantities. It does not change the analysis result; it only changes what is plotted and what curve is sent to cleanup or figures.

## Controls

| Control | What it does |
| --- | --- |
| **y** dropdown | Chooses the derived quantity plotted on the vertical axis. |
| **x: time -> strain** | Switches the horizontal axis from time to true strain. The button text changes to **x: strain -> time** when strain mode is active. |
| **Negate x** | Multiplies the displayed x values by `-1`. |
| **Negate y** | Multiplies the displayed y values by `-1`. |
| **Send to cleanup ->** | Sends the currently displayed `(x, y)` curve to the Curve cleanup tab. |
| **Send to figures ->** | Adds the currently displayed curve to the Figures tab. |

## Available Y Quantities

| Quantity | Backend value | Meaning |
| --- | --- | --- |
| `strain rate e_dot` | `eps_rate_eng` | Engineering strain rate. |
| `v_in` | `v_in` | Velocity at the input/specimen side. |
| `v_out` | `v_out` | Velocity at the output/specimen side. |
| `striker velocity` | `v_striker` | Striker velocity estimate from the incident pulse. |
| `u_in` | `u_in` | Input-side displacement. |
| `u_out` | `u_out` | Output-side displacement. |
| `f_in` | `f_in` | Input-side force. |
| `f_out` | `f_out` | Output-side force. |
| `eng. stress` | `str_eng` | Engineering stress. |
| `true stress` | `str_true` | True stress. |

## When To Use It

Use Explore when you need to inspect a signal that is not one of the fixed Analysis plots, compare a derived quantity against true strain, or pass a non-standard curve into cleanup or figure assembly.
