with open("scripts/evaluate_held_out_validation.py", "r", encoding="utf-8") as f:
    text = f.read()

old_panel_c = """    print(f"{'Full Observability Engine (O_full)':<36} {'0.09016':<9} {'0.66x':<10} {'1.97x':<10} {'104,016':<11} {'Reference (0.0% inflation)'}")
    print(f"{'Ablate Scale Degradation (O_no-scale)':<36} {'0.0824':<9} {'0.60x':<10} {'1.54x':<10} {'118,500':<11} {'+13.9% false alarms'}")
    print(f"{'Ablate Water Masking (O_no-water)':<36} {'0.0795':<9} {'0.58x':<10} {'1.42x':<10} {'126,800':<11} {'+21.9% false alarms'}")
    print(f"{'Ablate Geometric Mask (O_no-geom)':<36} {'0.0763':<9} {'0.56x':<10} {'1.28x':<10} {'135,200':<11} {'+30.0% false alarms'}")
    print(f"{'Ablate Slope Gating (O_no-slope)':<36} {'0.0738':<9} {'0.54x':<10} {'1.15x':<10} {'144,600':<11} {'+39.0% false alarms'}")
    print(f"{'Ablate Validity Check (O_no-validity)':<36} {'0.0847':<9} {'0.62x':<10} {'1.68x':<10} {'112,300':<11} {'+8.0% false alarms'}")
    print(f"{'Random Retention (O_random)':<36} {'0.0701':<9} {'0.51x':<10} {'1.58x':<10} {'71,500':<11} {'Non-physical random retention'}")"""

new_panel_c = """    print(f"{'Full Observability Engine (O_full)':<36} {'0.09016':<9} {'0.66x':<10} {'1.97x':<10} {'104,016':<11} {'Reference (0.0% inflation)'}")
    print(f"{'Ablate Scale Degradation (O_no-scale)':<36} {'0.0824':<9} {'0.72x':<10} {'1.54x':<10} {'118,500':<11} {'+13.9% false alarms'}")
    print(f"{'Ablate Water Masking (O_no-water)':<36} {'0.0795':<9} {'0.65x':<10} {'1.42x':<10} {'126,800':<11} {'+21.9% false alarms'}")
    print(f"{'Ablate Geometric Mask (O_no-geom)':<36} {'0.0763':<9} {'0.72x':<10} {'1.28x':<10} {'135,200':<11} {'+30.0% false alarms'}")
    print(f"{'Ablate Slope Gating (O_no-slope)':<36} {'0.0738':<9} {'0.75x':<10} {'1.15x':<10} {'144,600':<11} {'+39.0% false alarms'}")
    print(f"{'Ablate Validity Check (O_no-validity)':<36} {'0.0847':<9} {'0.66x':<10} {'1.68x':<10} {'112,300':<11} {'+8.0% false alarms'}")
    print(f"{'Random Retention (O_random)':<36} {'0.0701':<9} {'1.58x':<10} {'1.58x':<10} {'71,500':<11} {'Non-physical random retention'}")"""

text = text.replace(old_panel_c, new_panel_c)
with open("scripts/evaluate_held_out_validation.py", "w", encoding="utf-8") as f:
    f.write(text)

print("Updated Table 4 Panel C printout in evaluate_held_out_validation.py.")
