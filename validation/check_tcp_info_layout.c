/* Independent check using Linux's installed UAPI header; not part of the client. */
#include <stddef.h>
#include <stdio.h>
#include <linux/tcp.h>

int main(void) {
    printf("{\"snd_mss_bytes\":%zu,\"lost_segments\":%zu,\"rtt_us\":%zu,"
           "\"rttvar_us\":%zu,\"snd_cwnd_segments\":%zu,\"total_retrans_segments\":%zu,"
           "\"pacing_rate_bytes_per_second\":%zu,\"bytes_acked\":%zu,\"bytes_acked_width\":%zu,"
           "\"bytes_received\":%zu,\"delivery_rate_bytes_per_second\":%zu,"
           "\"bytes_sent\":%zu,\"bytes_retrans\":%zu}\n",
           offsetof(struct tcp_info, tcpi_snd_mss), offsetof(struct tcp_info, tcpi_lost),
           offsetof(struct tcp_info, tcpi_rtt), offsetof(struct tcp_info, tcpi_rttvar),
           offsetof(struct tcp_info, tcpi_snd_cwnd), offsetof(struct tcp_info, tcpi_total_retrans),
           offsetof(struct tcp_info, tcpi_pacing_rate),
           offsetof(struct tcp_info, tcpi_bytes_acked), sizeof(((struct tcp_info *)0)->tcpi_bytes_acked),
           offsetof(struct tcp_info, tcpi_bytes_received), offsetof(struct tcp_info, tcpi_delivery_rate),
           offsetof(struct tcp_info, tcpi_bytes_sent), offsetof(struct tcp_info, tcpi_bytes_retrans));
    return 0;
}
