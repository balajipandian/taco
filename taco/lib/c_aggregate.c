#include <stdio.h>
#include <Python.h>

static PyObject* py_fizzbuzz(PyObject* self, PyObject* args)
{
    int value;
    for (int i=1; i <= 10; i++){
        if (i % 3 == 0 && i % 5 ==0){
            printf("fizzbuzz %d \n", i);
            }
        else if (i % 3 == 0){
            printf("fizz %d \n", i);
            }
        else if(i % 5 == 0){
            printf("buzz %d \n", i); 
            }
        }

    // Return value.
    return Py_BuildValue("i", 0);

}

// Mapping between python and c function names. 
static PyMethodDef fizzbuzzModule_methods[] = {
    	{"fizzbuzz", py_fizzbuzz, METH_VARARGS},
    	{NULL, NULL}
    };

// Module initialisation routine.
void initfizzbuzz(void)
{
    // Init module.
    (void) Py_InitModule("fizzbuzz", fizzbuzzModule_methods);
}


