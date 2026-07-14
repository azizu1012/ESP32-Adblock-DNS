#pragma once
#ifdef __cplusplus
extern "C" {
#endif

void dns_optimizer_init(void);
extern char g_upstream_ip[16];
extern int g_upstream_rtt;

void dns_optimizer_get_upstream(char* out_ip, int* out_rtt);
void dns_optimizer_set_upstream(const char* ip, int rtt);

#ifdef __cplusplus
}
#endif

