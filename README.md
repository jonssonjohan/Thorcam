# Thorcam
My adaptation of a camera handler for a Thorlabs scientific camera. The handler is a object which makes it more modular and it it also thread based. Two images are collected and put into a queue. The queue can be shared with another thread which fetch and display and/or save the images. The code is based on SDK's from Thorlabs
