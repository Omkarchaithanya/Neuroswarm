#include <stddef.h>
#include <stdint.h>

void* mte_share_kv(void* kv_page, size_t size, uint8_t producer_tag) {
    (void)size;
    (void)producer_tag;
    return kv_page;
}

