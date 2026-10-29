#!/usr/bin/env python3
"""Apply the frequency-cap change by text anchors (works even if line numbers differ).
usage: python apply_freqcap.py   (run inside the kernel repo folder)"""
import sys

def edit(path, pairs):
    s = open(path).read()
    if "acme_build_cap" in s or "ACME_BIG_MAX_FREQ" in s:
        print("already applied:", path); return
    for old, new in pairs:
        if s.count(old) != 1:
            print("ERROR: anchor not found exactly once in %s:\n%s" % (path, old)); sys.exit(1)
        s = s.replace(old, new)
    open(path, "w").write(s)
    print("patched", path)

helper = '''/*
 * Optional build-time maximum frequency cap (kHz) per cluster.
 * 0 means no cap. CPU0 is in the little cluster, CPU4 in the big one.
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
a1 = "static __init int init_domain(struct exynos_cpufreq_domain *domain,"
a2 = "\tunsigned int val;\n\tint ret;\n\n\tmutex_init(&domain->lock);"
a3 = "\t\tdomain->min_freq = max(domain->min_freq, val);\n"
a4 = "\t\t/* change domain->max_freq to maximum level in boost table */"
edit("drivers/cpufreq/exynos-acme.c", [
    (a1, helper + a1),
    (a2, a2.replace("unsigned int val;", "unsigned int val, cap;")),
    (a3, a3 + '''
	cap = acme_build_cap(domain);
	if (cap && cap >= domain->min_freq) {
		domain->max_freq = min(domain->max_freq, cap);
		pr_info("ACME: cpus %*pbl max freq capped to %u kHz\\n",
			cpumask_pr_args(&domain->cpus), domain->max_freq);
	}
'''),
    (a4, '''		/* keep turbo/boost levels under the build-time cap too */
		if (cap && cap >= domain->min_freq)
			for (i = 0; i < cpu_count; i++)
				domain->boost_max_freqs[i] =
					min(domain->boost_max_freqs[i], cap);

''' + a4),
])
k = "config ARM_EXYNOS_UFC\n"
edit("drivers/cpufreq/Kconfig.arm", [(k, '''config ARM_EXYNOS_ACME_LITTLE_MAX_FREQ
	int "Max frequency cap for the little cluster in kHz (0 = no cap)"
	depends on ARM_EXYNOS_ACME
	default 0

config ARM_EXYNOS_ACME_BIG_MAX_FREQ
	int "Max frequency cap for the big cluster in kHz (0 = no cap)"
	depends on ARM_EXYNOS_ACME
	default 0

''' + k)])
