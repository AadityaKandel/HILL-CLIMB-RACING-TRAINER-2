from tkinter import *
import tkinter.messagebox as tmsg
from ReadWriteMemory import ReadWriteMemory
import win32api
import win32process
import win32con
import os

root = Tk()
root.iconbitmap('Icon/icon.ico')

# Variables
name="HILL CLIMB RACING"
not_found=f"{name} NOT FOUND!\nOPEN THE GAME & LAUNCH THE TRAINER AGAIN!!!"
found=f"{name} FOUND!!\nHAVE FUN WITH YOUR MOD!!"
info=f'''{name} TRAINER BY
www.github.com/AADITYAKANDEL
'''
font="comicsansms 11 bold"

# Customizing The Root
root.minsize(400,200)
root.maxsize(400,200)
root.title(f"{name} Trainer +2")

# Functions
def get_base_address(process_name):

	pid=''

	os.system(f'tasklist /fi "imagename eq {process_name}" > data.txt')
	f = open('data.txt','r')
	text = f.read()
	initial = text.index('HillClimbRacing.exe')
	finall = text.index('Console')
	total = text[initial:finall]

	for x in total:
		if x.isnumeric() == True:
			pid+=x
		else:
			pass

	f.close()



	process_name = process_name  # Replace with the actual process name
	process_access = win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ
	process_handle = win32api.OpenProcess(process_access, False, int(pid))

	base_addresss = win32process.EnumProcessModules(process_handle)[0]

	win32api.CloseHandle(process_handle)

	return base_addresss

# Getting Base Address & Defining Special Variables
base_address=get_base_address("hillclimbracing.exe")
coin_var = IntVar()
diamond_var = IntVar()
game=None
rm = ReadWriteMemory()
coins=base_address+0x28CAD4
diamonds=base_address+0x28CAEC
idiot="That's too big!! YOU IDIOT!!"
maximum=999999999

def check_if_numeric():
	try:
		add=coin_var.get()+diamond_var.get()
	except:
		tmsg.showwarning('Warning','Invalid Input')
		return False

def find_process():
	global game
	try:
		game = rm.get_process_by_name('HillClimbRacing.exe')
		game.open()
		return True
	except:
		return False

def detect_process():
	if find_process() == False:
		tmsg.showwarning('Warning',not_found)
		root.destroy()
	else:
		pass

def find_coins():
	coin_value = game.read(coins)
	coin_var.set(coin_value)

def find_diamonds():
	diamond_value=game.read(diamonds)
	diamond_var.set(diamond_value)

def modify_coins():
	if check_if_numeric() == False:
		pass
	else:
		if coin_var.get() > maximum:
			tmsg.showwarning('Warning',idiot)
		else:
			game.write(coins, coin_var.get())
			tmsg.showinfo('Success','Check Your Coins!!!')

def modify_diamonds():
	if check_if_numeric() == False:
		pass
	else:
		if diamond_var.get() > maximum:
			tmsg.showwarning('Warning',idiot)
		else:
			game.write(diamonds, diamond_var.get())
			tmsg.showinfo('Success','Check Your Diamond!!!')


l1 = Label(text=info,fg="white",bg="black",font=font)
l1.pack()

# Frame 1
f1 = Frame(background="black",borderwidth=10)

l2 = Label(f1,text="Coins:",bg="black",fg="white", font=font)
en2 = Entry(f1,textvariable=coin_var,width=10, font="comicsansms 12 italic")
btn3 = Button(f1,text="Set",bg="white",fg="black",border=1,font=font,width=5,command=modify_coins)

l2.pack(side=LEFT)
en2.pack(side=LEFT,padx=6)
btn3.pack(side=LEFT)

# Frame 2
f2 = Frame(background="black",borderwidth=5)

l3 = Label(f2,text="Diamond:",bg="black",fg="white", font=font)
en3 = Entry(f2,textvariable=diamond_var,width=10,font="comicsansms 12 italic")
btn5 = Button(f2,text="Set",bg="white",fg="black",font=font,border=1,width=5,command=modify_diamonds)

l3.pack(side=LEFT)
en3.pack(side=LEFT,padx=6)
btn5.pack(side=LEFT)


f1.pack(anchor=N)
f2.pack(anchor=N)


root.config(bg="black")

# Running Required Functions
detect_process()
find_coins()
find_diamonds()

root.mainloop()
