idf_component_register(SRCS "dns_server.cpp" "bloom_filter.cpp" "dns_optimizer.cpp" "gct_verifier.cpp"
                    INCLUDE_DIRS "include"
                    REQUIRES spiffs sys_manager)
