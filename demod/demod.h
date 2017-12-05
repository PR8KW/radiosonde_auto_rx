
int read_wav_header(FILE*, float);
int f32buf_sample(FILE*, int, int);
int read_sbit(FILE*, int, int*, int, int, int, int);

int getmaxCorr(float*, unsigned int*, int);
int headcmp(int, char*, int, int);
float get_var(void);

int init_buffers(char*, int, int, int);
int free_buffers(void);

unsigned int get_sample(void);

