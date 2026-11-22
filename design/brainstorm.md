# Design
## Project Ideas
* coupon/deal finder
* choose your own adventure game
* **Faeric language translator**
* translator?

### Interests
* Superheroes
* Star Wars
* Harry Potter
* Drawing
* Reading
* Movies
* Video Games
* Music
    * Listening
    * Piano
    * Ukulele
* Board Games+
    * DND
        * Faeric language translator
    * MTG
    * Villainous

## Pitch
### Faeric Language Translator/Language Builder
I have the beginnings of an original language I created for DND. This project can serve as a way to flesh it out, and create a translator app that can take simple English and translate it into Faeric, and vice versa.

After some discussion, the app will also be able to define user inputted translations to fill gaps. I'm going to try to generalize the app so that it can allow for user-defined languages.

Hello
![img](/sources/faeric-hello-snip.jpg)
To and from </br> 
Travel </br>
![img](/sources/travel_runes-edited.png)

### Questions to answer
1. Why are you interested in this project?
    - I am excited to work more on projects related to my homebrew DND world.
    - I believe this can be applied to other original or spoken languages.
2. What problem does your project solve, or what becomes better for having it?
    - The project will provide an efficient and quick means of translating words or small phrases, instead of me having to scroll my google doc.
    - Additionally, this can serve as a language-maker
3. What technologies are you considering to use?
    - Python: translation, tokenization, word lookup, grammar application
    - Flask: Web Interface?
    - MongoDB with PyMongo: persistent data storage (lexicon, language rules, translation history)
    - HTML + CSS: UI
    - GitHub: repo and final report.

## Diagram
![img](/diagram.png)

# Future Codex Prompts

# Scaling and End Goal
## Online Deployment
* only allow 5 unapproved suggestions to be sent by an individual user, the rest are saved on the account until the others are approved
* throw unapproved suggestions on a queue or something similar for the admin (me) to access and approve
* approved suggestions should propogate to all users

## Local Use
* spend time  adding to local dictionary in app to flesh out Faeric as much as possible
* include translation rules
    - only long vowels
    - English short vowels -> eliminated or replaced with glottal stop marked by an apostraphe
    - English to Latin/Spanish then apply rules. Then mangle
* UI: Sun & Moon or White vs. Black Sun

## End Goal
Something *I* can pull up and use without needing to run it locally.
* Doesn't need to be public
* Doesn't need to be hosted online