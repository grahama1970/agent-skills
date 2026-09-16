/* Synthetic access probes. Never reads protected content, sends it, or contacts a vendor.
 * The parent process first establishes unconfined positive controls.
 * Inputs: allowed file, denied canary, other PID environ, Unix socket, TCP4/6 ports, label.
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <unistd.h>

static bool open_ok(const char *p) { int fd=open(p,O_RDONLY); if(fd<0) return false; close(fd); return true; }
static bool denied(const char *p) { int fd=open(p,O_RDONLY); int e=errno; if(fd>=0){close(fd);return false;} return e==EACCES || e==EPERM; }
static bool label_ok(const char *wanted) {
    char buf[256]={0}; int fd=open("/proc/self/attr/current",O_RDONLY); if(fd<0)return false;
    ssize_t n=read(fd,buf,sizeof(buf)-1); close(fd); if(n<=0)return false;
    buf[strcspn(buf,"\n")]=0; return strcmp(buf,wanted)==0;
}
static bool network_denied(int family, const char *port) {
    int fd=socket(family,SOCK_STREAM,0);
    if(fd<0)return errno==EACCES || errno==EPERM || errno==EAFNOSUPPORT;
    struct timeval timeout={.tv_sec=2,.tv_usec=0}; setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&timeout,sizeof(timeout));
    int rc;
    if(family==AF_INET){struct sockaddr_in a={.sin_family=AF_INET,.sin_port=htons(atoi(port))};inet_pton(AF_INET,"127.0.0.1",&a.sin_addr);rc=connect(fd,(void*)&a,sizeof(a));}
    else {struct sockaddr_in6 a={.sin6_family=AF_INET6,.sin6_port=htons(atoi(port))};inet_pton(AF_INET6,"::1",&a.sin6_addr);rc=connect(fd,(void*)&a,sizeof(a));}
    int e=errno;close(fd);
    return rc<0 && (e==EPERM || e==EACCES || e==ENETUNREACH || e==EHOSTUNREACH || e==ECONNREFUSED || e==EINPROGRESS);
}
static bool unix_denied(const char *path) {
    int fd=socket(AF_UNIX,SOCK_STREAM,0); if(fd<0)return errno==EACCES || errno==EPERM;
    struct sockaddr_un a={.sun_family=AF_UNIX};snprintf(a.sun_path,sizeof(a.sun_path),"%s",path);
    int rc=connect(fd,(void*)&a,sizeof(a));int e=errno;close(fd);return rc<0 && (e==EPERM || e==EACCES);
}
static const char *j(bool b){return b?"true":"false";}
int main(int argc,char **argv){
    if(argc!=8)return 64;
    struct __user_cap_header_struct h={.version=_LINUX_CAPABILITY_VERSION_3,.pid=0};
    struct __user_cap_data_struct d[2]={{0},{0}};
    bool caps=syscall(SYS_capget,&h,&d)==0;
    for(int i=0;i<2;i++)caps=caps && !d[i].effective && !d[i].permitted && !d[i].inheritable;
    bool child=false;pid_t pid=fork();
    if(pid==0)_exit(label_ok(argv[7])?0:1);
    if(pid>0){int status=0;waitpid(pid,&status,0);child=WIFEXITED(status)&&WEXITSTATUS(status)==0;}
    printf("{\"schema_version\":\"ubuntu_service_privacy.probe_result.v1\",\"allowed_read\":%s,\"denied_read\":%s,\"denied_proc\":%s,\"denied_unix\":%s,\"denied_ipv4\":%s,\"denied_ipv6\":%s,\"no_capabilities\":%s,\"no_new_privileges\":%s,\"profile_attached\":%s,\"child_inherits\":%s}\n",
        j(open_ok(argv[1])),j(denied(argv[2])),j(denied(argv[3])),j(unix_denied(argv[4])),
        j(network_denied(AF_INET,argv[5])),j(network_denied(AF_INET6,argv[6])),j(caps),
        j(prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)==1),j(label_ok(argv[7])),j(child));
    return 0;
}
