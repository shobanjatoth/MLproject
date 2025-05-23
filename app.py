import numpy as np
import pandas as pd
from flask import Flask, render_template, request
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import pickle
import requests
import re
from bs4 import BeautifulSoup
from tmdbv3api import TMDb, Movie

# TMDb API setup
tmdb = TMDb()
tmdb.api_key = '72d19966f145a12485b7033ed0526058'

# Load NLP model and vectorizer
clf = pickle.load(open('nlp_model1.pkl', 'rb'))
vectorizer = pickle.load(open('tranform1.pkl', 'rb'))

def create_sim():
    data = pd.read_csv('main_data.csv')
    cv = CountVectorizer()
    count_matrix = cv.fit_transform(data['comb'])
    sim = cosine_similarity(count_matrix)
    return data, sim

def rcmd(m):
    global data, sim
    m = m.lower()
    try:
        data.head()
        sim.shape
    except:
        data, sim = create_sim()
    if m not in data['movie_title'].unique():
        return 'Sorry! The movie you searched is not in our database. Please check the spelling or try with some other movies'
    else:
        i = data.loc[data['movie_title'] == m].index[0]
        lst = list(enumerate(sim[i]))
        lst = sorted(lst, key=lambda x: x[1], reverse=True)
        lst = lst[1:11]
        l = [data['movie_title'][x[0]] for x in lst]
        return l

def ListOfGenres(genre_json):
    return ", ".join([g['name'] for g in genre_json]) if genre_json else "N/A"

def date_convert(s):
    MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December']
    y = s[:4]
    m = int(s[5:7])
    d = s[8:10]
    return f"{MONTHS[m - 1]} {d}, {y}"

def MinsToHours(duration):
    return f"{duration // 60} hours {duration % 60} minutes" if duration else "N/A"

def get_suggestions():
    data = pd.read_csv('main_data.csv')
    return list(data['movie_title'].str.capitalize())

def clean_review(text):
    text = BeautifulSoup(text, "html.parser").get_text()
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"[^a-zA-Z0-9.,!?'\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]

def get_trailer_url(movie_id):
    try:
        video_response = requests.get(
            f'https://api.themoviedb.org/3/movie/{movie_id}/videos?api_key={tmdb.api_key}'
        )
        videos = video_response.json().get('results', [])
        for video in videos:
            if video['type'] == 'Trailer' and video['site'] == 'YouTube':
               
                return f"https://www.youtube.com/embed/{video['key']}"
    except:
        return None
    return None

def get_poster_url(movie_id):
    response = requests.get(f'https://api.themoviedb.org/3/movie/{movie_id}?api_key={tmdb.api_key}')
    data_json = response.json()
    poster_path = data_json.get('poster_path', '')
    if poster_path:
        return f"https://image.tmdb.org/t/p/original{poster_path}"
    return "https://via.placeholder.com/300x450?text=No+Image"

app = Flask(__name__)

@app.route("/")
def home():
    suggestions = get_suggestions()
    return render_template('home.html', suggestions=suggestions)

@app.route("/recommend")
def recommend():
    movie = request.args.get('movie')
    if not movie:
        return "Movie parameter is missing!", 400

    r = rcmd(movie)
    movie = movie.upper()
    suggestions = get_suggestions()

    if isinstance(r, str):
        return render_template(
            'recommend.html',
            movie=movie,
            r=r,
            t='s',
            suggestions=suggestions,
            result=None,
            cards={},
            reviews={},
            img_path="",
            genres="N/A",
            vote_count="N/A",
            release_date="N/A",
            status="N/A",
            runtime="N/A",
            trailer_url=None
        )

    tmdb_movie = Movie()
    result = tmdb_movie.search(movie)
    if not result:
        return render_template(
            'recommend.html',
            movie=movie,
            r="Movie not found in TMDb!",
            t='s',
            suggestions=suggestions,
            result=None,
            cards={},
            reviews={},
            img_path="",
            genres="N/A",
            vote_count="N/A",
            release_date="N/A",
            status="N/A",
            runtime="N/A",
            trailer_url=None
        )

    movie_id = result[0].id
    movie_name = result[0].title

    response = requests.get(f'https://api.themoviedb.org/3/movie/{movie_id}?api_key={tmdb.api_key}')
    data_json = response.json()
    poster = data_json.get('poster_path', '')
    img_path = f'https://image.tmdb.org/t/p/original{poster}' if poster else ""
    genre = ListOfGenres(data_json.get('genres', []))
    trailer_url = get_trailer_url(movie_id)

    movie_reviews = {}
    try:
        review_response = requests.get(
            f'https://api.themoviedb.org/3/movie/{movie_id}/reviews?api_key={tmdb.api_key}'
        )
        reviews_list = review_response.json().get('results', [])

        if reviews_list:
            for review in reviews_list:
                raw_content = review.get('content', '')
                author = review.get('author', 'Anonymous')
                created_at = review.get('created_at', '')[:10]
                rating = review.get('author_details', {}).get('rating', 'N/A')

                clean_text = clean_review(raw_content)
                if clean_text:
                    movie_vector = vectorizer.transform([clean_text])
                    pred = clf.predict(movie_vector)
                    sentiment = 'Good' if pred else 'Bad'
                    key = f'"{author}" on {created_at} (Rating: {rating})'
                    movie_reviews[key] = {'review': clean_text, 'sentiment': sentiment}
        else:
            movie_reviews = {"Notice": {"review": "No reviews available on TMDb.", "sentiment": "N/A"}}
    except:
        movie_reviews = {"Error": {"review": "Failed to fetch TMDb reviews.", "sentiment": "N/A"}}

    vote_count = "{:,}".format(result[0].vote_count)
    rd = date_convert(result[0].release_date)
    status = data_json.get('status', 'Unknown')
    runtime = MinsToHours(data_json.get('runtime', 0))

    movie_cards = {}
    for movie_title in r:
        list_result = tmdb_movie.search(movie_title)
        if list_result:
            rec_id = list_result[0].id
            rec_response = requests.get(f'https://api.themoviedb.org/3/movie/{rec_id}?api_key={tmdb.api_key}')
            rec_data = rec_response.json()
            poster_url = f"https://image.tmdb.org/t/p/original{rec_data.get('poster_path', '')}"
            rec_trailer = get_trailer_url(rec_id)
            movie_cards[movie_title] = {
                'poster': poster_url,
                'trailer': rec_trailer
            }

    return render_template('recommend.html',
                           movie=movie,
                           mtitle=r,
                           t='l',
                           cards=movie_cards,
                           result=result[0],
                           reviews=movie_reviews,
                           img_path=img_path,
                           genres=genre,
                           vote_count=vote_count,
                           release_date=rd,
                           status=status,
                           runtime=runtime,
                           trailer_url=trailer_url,
                           suggestions=suggestions)

if __name__ == '__main__':
    app.run(debug=True)