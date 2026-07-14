#pragma once
#ifdef __cplusplus
extern "C" {
#endif

void dns_optimizer_init(void);
extern char g_upstream_ip[16];
extern int g_upstream_rtt;

#ifdef __cplusplus
}
#endif
