import useUser from "../../hooks/useUser";

import "./Sidebar.css";

export default function Sidebar({

    currentPage,

    setCurrentPage,

}) {

    const {

        user,

        loading,

    } = useUser();

    return (

        <aside className="sidebar">

            <div className="sidebar-logo">

                CipherChat

            </div>

            <div className="sidebar-profile">

                <div className="avatar">

                    👤

                </div>

                {

                    loading

                        ?

                        (

                            <h3>

                                Loading...

                            </h3>

                        )

                        :

                        (

                            <>

                                <h3>

                                    {

                                        user?.display_name ||

                                        "Unknown User"

                                    }

                                </h3>

                                <p>

                                    {

                                        user?.email

                                    }

                                </p>

                            </>

                        )

                }

            </div>

            <nav className="sidebar-menu">

                <button

                    className={

                        currentPage === "chats"

                            ? "active"

                            : ""

                    }

                    onClick={() =>

                        setCurrentPage(

                            "chats"

                        )

                    }

                >

                    💬 Chats

                </button>

                <button

                    className={

                        currentPage === "friends"

                            ? "active"

                            : ""

                    }

                    onClick={() =>

                        setCurrentPage(

                            "friends"

                        )

                    }

                >

                    👥 Friends

                </button>

                <button

                    className={

                        currentPage === "settings"

                            ? "active"

                            : ""

                    }

                    onClick={() =>

                        setCurrentPage(

                            "settings"

                        )

                    }

                >

                    ⚙ Settings

                </button>

            </nav>

        </aside>

    );

}