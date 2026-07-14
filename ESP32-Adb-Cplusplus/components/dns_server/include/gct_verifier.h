#pragma once
#ifdef __cplusplus
extern "C" {
#endif

void gct_verifier_init(void);
void gct_queue_domain(const char* domain);
bool is_domain_in_safelist_dyn(const char* domain);

#ifdef __cplusplus
}
#endif
