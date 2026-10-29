#!/usr/bin/env python3
"""Freq cap v2: enforce the cap with an extra PM QoS max request, leaving the
frequency table (and thermal cooling levels) untouched. Run in the kernel repo folder."""
import sys

def rd(p): return open(p).read()
def wr(p, s): open(p, "w").write(s)
def sub(s, old, new, label):
    if s.count(old) != 1:
        print("ERROR: anchor not found for", label); sys.exit(1)
    return s.replace(old, new)

C = "drivers/cpufreq/exynos-acme.c"
H = "drivers/cpufreq/exynos-acme.h"
K = "drivers/cpufreq/Kconfig.arm"

s = rd(C)
if "cap_qos_req" in s:
    print("v2 already applied")
else:
    # remove v1 pieces if present
    v1a = '''
	cap = acme_build_cap(domain);
	if (cap && cap >= domain->min_freq) {
		domain->max_freq = min(domain->max_freq, cap);
		pr_info("ACME: cpus %*pbl max freq capped to %u kHz\\n",
			cpumask_pr_args(&domain->cpus), domain->max_freq);
	}
'''
    v1b = '''		/* keep turbo/boost levels under the build-time cap too */
		if (cap && cap >= domain->min_freq)
			for (i = 0; i < cpu_count; i++)
				domain->boost_max_freqs[i] =
					min(domain->boost_max_freqs[i], cap);

'''
    if v1a in s:
        s = s.replace(v1a, "").replace(v1b, "").replace("unsigned int val, cap;", "unsigned int val;")
    helper = '''/*
 * Optional build-time maximum frequency cap (kHz) per cluster, 0 = none.
 * CPU0 is in the little cluster, CPU4 in the big one.
 */
static __init unsigned int acme_build_cap(struct exynos_cpufreq_domain *domain)
{
#ifdef CONFIG_ARM_EXYNOS_ACME_LITTLE_MAX_FREQ
	if (cpumask_test_cpu(0, &domain->cpus))
		return CONFIG_ARM_EXYNOS_ACME_LITTLE_MAX_FREQ;
#endif
#ifdef CONFIG_ARM_EXYNOS_ACME_BIG_MAX_FREQ
	if (cpumask_test_cpu(4, &domain->cpus))
		return CONFIG_ARM_EXYNOS_ACME_BIG_MAX_FREQ;
#endif
	return 0;
}

'''
    if "acme_build_cap" not in s:
        a1 = "static __init int init_domain(struct exynos_cpufreq_domain *domain,"
        s = sub(s, a1, helper + a1, "init_domain")
    a3 = "\t\tdomain->min_freq = max(domain->min_freq, val);\n"
    s = sub(s, a3, a3 + '''
	domain->cap_freq = acme_build_cap(domain);
	if (domain->cap_freq && domain->cap_freq < domain->min_freq)
		domain->cap_freq = 0;
''', "min-freq")
    a4 = '''	pm_qos_add_request(&domain->max_qos_req,
			domain->pm_qos_max_class, domain->max_freq);
'''
    s = sub(s, a4, a4 + '''
	if (domain->cap_freq && domain->cap_freq < domain->max_freq) {
		pm_qos_add_request(&domain->cap_qos_req,
				domain->pm_qos_max_class, domain->cap_freq);
		pr_info("ACME: cpus %*pbl max freq capped to %u kHz\\n",
			cpumask_pr_args(&domain->cpus), domain->cap_freq);
	}
''', "init_pm_qos")
    wr(C, s)
    h = rd(H)
    h = sub(h, "\tstruct pm_qos_request\t\tmax_qos_req;\n",
            "\tstruct pm_qos_request\t\tmax_qos_req;\n\tstruct pm_qos_request\t\tcap_qos_req;\n\tunsigned int\t\t\tcap_freq;\n", "header")
    wr(H, h)
    print("patched driver")

k = rd(K)
if "ACME_BIG_MAX_FREQ" not in k:
    a = "config ARM_EXYNOS_UFC\n"
    k = sub(k, a, '''config ARM_EXYNOS_ACME_LITTLE_MAX_FREQ
	int "Max frequency cap for the little cluster in kHz (0 = no cap)"
	depends on ARM_EXYNOS_ACME
	default 0

config ARM_EXYNOS_ACME_BIG_MAX_FREQ
	int "Max frequency cap for the big cluster in kHz (0 = no cap)"
	depends on ARM_EXYNOS_ACME
	default 0

''' + a, "Kconfig")
    wr(K, k)
    print("patched Kconfig")
